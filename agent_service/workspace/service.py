"""云端项目工作区服务。

已实现（按任务说明）：
* 组长说明 §2「确认项目、准备根目录」+ §3.2 定位方案、Java 说明 §8 的
  ``PUT /api/internal/projects/{projectId}/workspace``；
* 组长说明 §4.1 + Java 说明 §6.1/§8 的目录浏览
  ``GET /api/internal/projects/{projectId}/files/tree``。

未实现（后续步骤按契约再补，不提前做）：文本预览、单文件下载、项目压缩、Git。
"""

import base64
import binascii
import hashlib
import hmac
import json
import os
import shutil
import stat
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterator
from urllib.parse import quote

from ..config import Settings
from .exception import WorkspaceError, WorkspaceErrorCode
from .models import (
    ENTRY_KIND_DIRECTORY,
    ENTRY_KIND_FILE,
    DirectoryPage,
    FileEntry,
    FilePreview,
    WorkspaceStatus,
)
from .policy import (
    ensure_project_directory,
    is_exportable,
    is_exportable_dir,
    is_previewable,
    is_valid_identifier,
    normalize_path,
    open_export_file,
    open_project_directory,
    resolve_project_directory,
)

# 游标有效期：过期必须重读第一页。文档未规定具体时长，取 15 分钟。
_CURSOR_TTL_SECONDS = 900
# 签名截断长度足够防篡改，同时让 URL 不至过长。
_CURSOR_MAC_BYTES = 16
# 下载分块大小：64 KiB 兼顾吞吐与单块内存占用。
_DOWNLOAD_CHUNK_BYTES = 65_536


def _b64url_encode(raw: bytes) -> str:
    """base64url 编码并去掉 ``=`` 填充，结果可直接放进 URL 查询参数。"""

    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    """base64url 解码，自动补齐被去掉的 ``=`` 填充。"""

    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _entry_sort_key(entry: FileEntry) -> tuple[int, str, str]:
    """目录在前；名称按大小写不敏感字典序；仍相同则按原名兜底。

    ``os.scandir`` 的顺序在 Windows 与 Linux 上都不可靠，必须自己排，
    否则用户每次刷新看到的顺序都可能不同。
    """

    return (
        0 if entry.kind == ENTRY_KIND_DIRECTORY else 1,
        entry.name.casefold(),
        entry.name,
    )


def _content_disposition(filename: str) -> str:
    """生成 RFC 6266 附件头：ASCII 兜底名 + UTF-8 百分号编码的真实文件名。

    兜底名里把引号、反斜杠和控制字符替换成下划线，避免头注入；真实文件名用
    ``filename*=`` 携带，浏览器才能正确显示中文名。
    """

    fallback = "".join(
        character
        if 0x20 <= ord(character) < 0x7F and character not in '"\\'
        else "_"
        for character in filename
    ) or "download"
    return (
        f'attachment; filename="{fallback}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


@dataclass(slots=True)
class DownloadHandle:
    """一次已就绪的单文件下载：句柄、文件名、字节数与释放名额的回调。

    调用方只需把 :meth:`iter_chunks` 交给流式响应；正常结束与客户端中途断开会
    走同一个 ``finally``，句柄和下载名额都会被释放，不需要调用方记得清理。
    """

    stream: BinaryIO
    filename: str
    size_bytes: int
    content_disposition: str
    release: Callable[[], None]
    _closed: bool = False

    def iter_chunks(self) -> Iterator[bytes]:
        """按块产出文件内容；结束时关闭句柄并归还下载名额（可重复调用关闭）。"""

        try:
            while True:
                chunk = self.stream.read(_DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                yield chunk
        finally:
            self.close()

    def close(self) -> None:
        """幂等关闭：先关句柄再还名额，重复调用不会重复归还。"""

        if self._closed:
            return
        self._closed = True
        try:
            self.stream.close()
        finally:
            self.release()


@dataclass(slots=True)
class ArchiveHandle:
    """一次已经生成完毕的项目 ZIP：临时文件、大小与清理回调。

    ZIP 在返回响应之前就完整生成并校验过，发送阶段只读这个临时文件；
    结束或客户端断开时删除临时文件并归还名额。
    """

    path: Path
    filename: str
    size_bytes: int
    content_disposition: str
    release: Callable[[], None]
    _closed: bool = False

    def iter_chunks(self) -> Iterator[bytes]:
        """按块产出 ZIP 字节；结束时删除临时文件并归还名额（可重复调用关闭）。"""

        try:
            with self.path.open("rb") as stream:
                while True:
                    chunk = stream.read(_DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    yield chunk
        finally:
            self.close()

    def close(self) -> None:
        """幂等清理：先删临时文件再还名额，重复调用安全。"""

        if self._closed:
            return
        self._closed = True
        try:
            self.path.unlink(missing_ok=True)
        finally:
            self.release()


@dataclass(slots=True)
class _UsageLease:
    """一次项目使用占用的凭证；只有持有它的调用方才能释放。"""

    project_id: str
    kind: str
    released: bool = False


class ProjectUsageRegistry:
    """进程内的"项目正在被谁使用"标记表。

    文档 §6.1 要求 Agent、项目打包和 Git 共用同一套标记：各自锁自己会互不认识。
    这里只保存活动项目，结束即移除，不按项目 UUID 永久留条目；单进程实现，
    将来多实例部署时换成 Redis 的同类语义。
    """

    def __init__(self) -> None:
        """创建空的活动项目表；构造时不分配额外资源。"""

        self._lock = threading.Lock()
        self._holders: dict[str, str] = {}

    def acquire(self, project_id: str, kind: str) -> _UsageLease | None:
        """尝试占用项目；已被占用时返回 None，由调用方翻译成 409。"""

        with self._lock:
            if project_id in self._holders:
                return None
            self._holders[project_id] = kind
            return _UsageLease(project_id=project_id, kind=kind)

    def release(self, lease: _UsageLease) -> None:
        """释放占用；重复释放安全，且不会误删别人刚取得的占用。"""

        with self._lock:
            if lease.released:
                return
            lease.released = True
            if self._holders.get(lease.project_id) == lease.kind:
                del self._holders[lease.project_id]

    def holder_kind(self, project_id: str) -> str | None:
        """返回当前占用者类型（agent/archive/git）；空闲时返回 None。"""

        with self._lock:
            return self._holders.get(project_id)


class WorkspaceService:
    """按可信归属准备云端项目目录，并提供受控的目录浏览。

    目录由服务端按 ``users/{owner_id}/projects/{project_id}`` 生成；模型与浏览器
    都不能指定路径。项目记录由 Java 先提交，Python 只读取 owner 后补建目录。
    """

    def __init__(self, settings: Settings, repository: Any | None = None) -> None:
        """保存配置与归属查询；构造时不碰磁盘、不连数据库。"""

        self.settings = settings
        # 归属查询与 Run 仓储共用同一个实例，避免准备目录和运行任务看到两套数据源。
        self.repository = repository
        # 下载名额：进程内计数，满了立刻拒绝而不是排队；名额在流结束时归还。
        self._download_slots = threading.BoundedSemaphore(
            max(1, settings.workspace_max_concurrent_downloads)
        )
        # 打包名额与项目使用标记：ZIP 与将来的 Agent/Git 共用同一套标记。
        self._archive_slots = threading.BoundedSemaphore(
            max(1, settings.workspace_max_concurrent_archives)
        )
        self.usage = ProjectUsageRegistry()
        self._cursor_key_cache: bytes | None = None

    # ---------------- 准备目录 ----------------

    def prepare_project(self, project_id: str) -> WorkspaceStatus:
        """准备项目目录；重复调用只补缺失目录，不清空文件、不重建 Git。

        失败时不删除项目记录、不删除已存在目录：调用方保留记录后可以重试，
        排查现场也不会被自己清掉。本地模式不使用云端工作区，直接拒绝。
        """
        if self.settings.execution_mode.lower() != "cloud":
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "本地模式不需要准备云端工作区"
            )
        root = self._workspace_root()
        owner_id = self._project_owner(project_id)
        # 创建与检查在同一处完成：逐层 lstat/mkdir，任何一层是链接都拒绝。
        ensure_project_directory(root, owner_id, project_id)
        return WorkspaceStatus(project_id=project_id, ready=True)

    # ---------------- 目录浏览 ----------------

    def list_directory(
        self,
        project_id: str,
        path: str | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> DirectoryPage:
        """列出项目内某个目录的直接子项（Java 说明 §6.1 的数据形状）。

        只扫一层，目录在前、名称稳定排序；条目按公开导出策略过滤，符号链接与
        设备文件不出现。分页用不透明游标，游标绑定项目与目录，目录在分页期间
        变化时返回 ``CURSOR_EXPIRED``，让前端重读第一页而不是拿到错位的结果。
        """
        self._ensure_cloud_mode()
        root = self._workspace_root()
        owner_id = self._project_owner(project_id)
        project_root = self._existing_project_root(root, owner_id, project_id)

        relative = normalize_path(path)
        if relative and not is_exportable_dir(relative):
            raise WorkspaceError(WorkspaceErrorCode.PATH_FORBIDDEN, "目录不允许浏览")
        size = self._page_size(page_size)
        # 从工作区根开始固定用户层/项目层，不能只固定项目内最后的子目录。
        with open_project_directory(root, project_root.relative_to(root).as_posix()) as project:
            with open_project_directory(project, relative) as directory:
                entries, fingerprint = self._scan_directory(directory, relative)

        offset = 0
        if cursor:
            offset, expected_fingerprint = self._decode_cursor(cursor, project_id, relative)
            if expected_fingerprint != fingerprint:
                raise WorkspaceError(
                    WorkspaceErrorCode.CURSOR_EXPIRED, "目录已变化，请重新读取第一页"
                )
            if offset > len(entries):
                raise WorkspaceError(
                    WorkspaceErrorCode.CURSOR_EXPIRED, "目录已变化，请重新读取第一页"
                )

        window = entries[offset:offset + size]
        next_cursor = None
        if offset + size < len(entries):
            next_cursor = self._encode_cursor(
                project_id, relative, offset + size, fingerprint
            )
        return DirectoryPage(
            project_id=project_id,
            path=relative,
            entries=tuple(window),
            next_cursor=next_cursor,
        )

    # ---------------- 文本预览 ----------------

    def read_text_preview(self, project_id: str, path: str | None = None) -> FilePreview:
        """读取一个允许预览的 UTF-8 文本文件（Java 说明 §6.2、组长说明 §4.2）。

        与文件工具的区别：返回**完整内容**和真实字节数，不复用 ``read_text_file``
        默认的 200 行截断。大小用打开句柄上的 ``fstat`` 判断，并且最多只读
        "上限 + 1 字节"，因此"检查后文件被写大"也不会把大文件读进内存。

        错误语义：不可导出、目录或特殊文件 → PATH_FORBIDDEN(404)；文件不存在 →
        ENTRY_NOT_FOUND(404)；非文本类型或非 UTF-8 → PREVIEW_UNSUPPORTED(415)；
        超上限 → PREVIEW_TOO_LARGE(413)。
        """
        self._ensure_cloud_mode()
        root = self._workspace_root()
        owner_id = self._project_owner(project_id)
        project_root = self._existing_project_root(root, owner_id, project_id)

        relative = normalize_path(path)
        if not relative:
            raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "预览必须指定文件路径")
        if not is_exportable(relative):
            # 和"不存在"使用同一个错误码，避免通过错误差异探测文件是否存在。
            raise WorkspaceError(WorkspaceErrorCode.PATH_FORBIDDEN, "目标文件不允许预览")

        limit = self.settings.workspace_max_preview_bytes
        if limit <= 0:
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "预览上限配置无效"
            )

        # 句柄同时承担"校验"和"读取"：大小信任 fstat，内容读同一个句柄。
        stream, info = open_export_file(project_root, relative)
        try:
            if not is_previewable(relative):
                raise WorkspaceError(
                    WorkspaceErrorCode.PREVIEW_UNSUPPORTED, "该文件类型不支持文本预览"
                )
            if info.st_size > limit:
                raise WorkspaceError(
                    WorkspaceErrorCode.PREVIEW_TOO_LARGE,
                    f"文件超过预览上限 {limit} 字节",
                )
            raw = stream.read(limit + 1)
        finally:
            stream.close()

        if len(raw) > limit:
            # 读到上限+1 说明打开后文件被写大，按超限处理，不截断冒充完整内容。
            raise WorkspaceError(
                WorkspaceErrorCode.PREVIEW_TOO_LARGE, f"文件超过预览上限 {limit} 字节"
            )

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            # 严格解码：不用 errors="replace" 把二进制或其它编码糊成乱码。
            raise WorkspaceError(
                WorkspaceErrorCode.PREVIEW_UNSUPPORTED, "文件不是 UTF-8 文本"
            ) from exc
        if content.startswith("\ufeff"):
            # 去掉 Windows 常见的一个 UTF-8 BOM；size_bytes 仍报真实字节数。
            content = content[1:]

        return FilePreview(
            project_id=project_id,
            path=relative,
            content=content,
            size_bytes=len(raw),
        )

    # ---------------- 单文件下载 ----------------

    def open_file_download(self, project_id: str, path: str | None = None) -> DownloadHandle:
        """打开一个允许导出的文件供流式下载（Java 说明 §6.3、组长说明 §4.3）。

        只负责校验、占用下载名额并固定文件本身；分块读取与关闭由路由负责。
        使用已固定的父目录句柄打开文件，不会因为路径被替换而读到别处。

        错误语义：不可导出、目录或链接 → PATH_FORBIDDEN(404)；不存在 →
        ENTRY_NOT_FOUND(404)；超过上限 → DOWNLOAD_TOO_LARGE(413)；
        下载名额已满 → DOWNLOAD_LIMIT(429)。
        """
        self._ensure_cloud_mode()
        root = self._workspace_root()
        owner_id = self._project_owner(project_id)
        project_root = self._existing_project_root(root, owner_id, project_id)

        relative = normalize_path(path)
        if not relative:
            raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "下载必须指定文件路径")
        if not is_exportable(relative):
            raise WorkspaceError(WorkspaceErrorCode.PATH_FORBIDDEN, "目标文件不允许下载")

        limit = self.settings.workspace_max_download_bytes
        if limit <= 0:
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "下载上限配置无效"
            )

        # 名额满时立刻拒绝：不排队、不占线程等待。
        if not self._download_slots.acquire(blocking=False):
            raise WorkspaceError(
                WorkspaceErrorCode.DOWNLOAD_LIMIT, "同时下载数量已达上限，请稍后重试"
            )
        try:
            stream, info = open_export_file(project_root, relative)
            if info.st_size > limit:
                stream.close()
                raise WorkspaceError(
                    WorkspaceErrorCode.DOWNLOAD_TOO_LARGE,
                    f"文件超过下载上限 {limit} 字节",
                )
        except BaseException:
            # 任何一步失败都要把名额还回去，否则会逐渐耗尽。
            self._download_slots.release()
            raise

        filename = relative.rpartition("/")[2]
        return DownloadHandle(
            stream=stream,
            filename=filename,
            size_bytes=info.st_size,
            content_disposition=_content_disposition(filename),
            release=self._download_slots.release,
        )

    # ---------------- 项目 ZIP ----------------

    def prepare_archive(self, project_id: str) -> ArchiveHandle:
        """把整个项目打包成 ZIP 临时文件，成功后才返回句柄（Java §6.4、组长 §4.4）。

        打包期间占用项目使用标记：Agent 正在运行、Git 收尾或已在打包都返回
        PROJECT_BUSY(409)。ZIP 生成完毕后立即释放项目标记，发送阶段只读临时文件，
        不再阻塞后续任务（文档 §4.4 明确允许）。

        失败时不返回半成品：临时文件删除、名额归还、项目标记释放。
        """
        self._ensure_cloud_mode()
        root = self._workspace_root()
        owner_id = self._project_owner(project_id)
        project_root = self._existing_project_root(root, owner_id, project_id)

        lease = self.usage.acquire(project_id, "archive")
        if lease is None:
            holder = self.usage.holder_kind(project_id) or "其他任务"
            raise WorkspaceError(
                WorkspaceErrorCode.PROJECT_BUSY, f"项目正在被{holder}占用，请稍后再试"
            )

        slot_acquired = False
        try:
            if not self._archive_slots.acquire(blocking=False):
                raise WorkspaceError(
                    WorkspaceErrorCode.DOWNLOAD_LIMIT, "同时打包数量已达上限，请稍后重试"
                )
            slot_acquired = True
            archive_path, size_bytes = self._build_archive(project_root)
        except BaseException:
            if slot_acquired:
                self._archive_slots.release()
            raise
        finally:
            # ZIP 已生成（或失败）后不再需要项目独占；发送阶段不占项目标记。
            self.usage.release(lease)

        filename = f"{project_id}.zip"
        return ArchiveHandle(
            path=archive_path,
            filename=filename,
            size_bytes=size_bytes,
            content_disposition=_content_disposition(filename),
            release=self._archive_slots.release,
        )

    def _build_archive(self, project_root: Path) -> tuple[Path, int]:
        """遍历项目生成 ZIP 临时文件，返回路径与字节数；超限/超时/出错即清理。"""

        max_files = self.settings.workspace_max_archive_files
        max_input = self.settings.workspace_max_archive_input_bytes
        max_output = self.settings.workspace_max_archive_bytes
        timeout = self.settings.workspace_archive_timeout_seconds
        if min(max_files, max_input, max_output, timeout) <= 0:
            # 打包限制必须是正数；配成 0 或负数会让限制失效（timeout=0 尤其危险：
            # 单调时钟分辨率内 elapsed 可能正好为 0，看起来像"已关闭"）。
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "打包限制配置无效"
            )
        started = time.monotonic()

        temp_root = self._archive_temp_root()
        try:
            temp_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "打包临时目录不可用"
            ) from exc

        descriptor, raw_path = tempfile.mkstemp(prefix="archive-", suffix=".zip", dir=temp_root)
        os.close(descriptor)
        archive_path = Path(raw_path)
        input_bytes = 0
        file_count = 0
        try:
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for relative in self._iter_exportable_files(project_root):
                    if time.monotonic() - started > timeout:
                        raise WorkspaceError(
                            WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "打包超时，已取消"
                        )
                    file_count += 1
                    if file_count > max_files:
                        raise WorkspaceError(
                            WorkspaceErrorCode.ARCHIVE_TOO_LARGE,
                            f"项目文件数超过上限 {max_files}",
                        )
                    stream, info = open_export_file(project_root, relative)
                    try:
                        input_bytes += info.st_size
                        if input_bytes > max_input:
                            raise WorkspaceError(
                                WorkspaceErrorCode.ARCHIVE_TOO_LARGE, "项目总字节超过上限"
                            )
                        # 边读边写，不把文件整块读进内存。
                        with archive.open(relative, "w") as target:
                            shutil.copyfileobj(stream, target, _DOWNLOAD_CHUNK_BYTES)
                    finally:
                        stream.close()
                    if archive_path.stat().st_size > max_output:
                        raise WorkspaceError(
                            WorkspaceErrorCode.ARCHIVE_TOO_LARGE, "ZIP 大小超过上限"
                        )
        except BaseException:
            archive_path.unlink(missing_ok=True)
            raise
        return archive_path, archive_path.stat().st_size

    def _iter_exportable_files(self, project_root: Path) -> Iterator[str]:
        """按公开导出策略遍历项目文件，产出项目内相对路径。

        不跟随链接、不进入排除目录；只交出普通单链接文件，链接与特殊文件直接
        跳过（它们不属于"公开导出"范围，也不应让整次打包失败）。
        """

        for current, dirnames, filenames in os.walk(project_root, followlinks=False):
            current_path = Path(current)
            relative_dir = current_path.relative_to(project_root).as_posix()
            prefix = "" if relative_dir == "." else f"{relative_dir}/"
            # 就地过滤目录名，os.walk 因此不会进入被排除的目录。
            dirnames[:] = [
                name for name in dirnames if is_exportable_dir(f"{prefix}{name}")
            ]
            for name in filenames:
                relative = f"{prefix}{name}"
                if not is_exportable(relative):
                    continue
                try:
                    info = os.lstat(current_path / name)
                except OSError:
                    continue
                if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    continue
                if info.st_nlink > 1:
                    # 多硬链接可能指向项目外，与单文件导出保持同一处置。
                    continue
                yield relative

    def _archive_temp_root(self) -> Path:
        """返回打包临时目录：专用子目录，绝不放进项目内（避免递归打包）。"""

        configured = self.settings.workspace_archive_temp_dir.strip()
        if configured:
            return Path(configured).expanduser()
        return Path(tempfile.gettempdir()) / "agent-service-archives"

    # ---------------- 内部：路径与归属 ----------------

    def _ensure_cloud_mode(self) -> None:
        """本地模式没有"云端工作区"概念，任何工作区操作都直接拒绝。

        这是**已确认的产品决定**（Java 说明 §6：四个文件接口先用于 cloud，local
        由前端提示"本地项目请使用自己的编辑器"）。返回 503 + 明确文案，而不是
        200 空树或 404，避免让前端误以为"项目是空的"。
        """

        if self.settings.execution_mode.lower() != "cloud":
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "本地模式不使用云端工作区"
            )

    def _workspace_root(self) -> Path:
        """返回受控工作区根目录；不存在时报不可用，不顺手创建它。"""

        root = Path(self.settings.workspace_root).expanduser()
        if not root.is_dir():
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "云端工作区根目录不存在"
            )
        return root

    def _project_owner(self, project_id: str) -> str:
        """取可信 owner；没有归属就拒绝，不给"猜一个目录"的兜底。"""
        if not is_valid_identifier(project_id):
            raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "项目标识不合法")
        if self.repository is None:
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "缺少项目归属查询"
            )
        try:
            owner_id = self.repository.get_project_owner(project_id)
        except Exception as exc:
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "无法读取项目归属", cause=exc
            ) from exc
        if not owner_id or not is_valid_identifier(owner_id):
            raise WorkspaceError(
                WorkspaceErrorCode.PROJECT_NOT_FOUND, "项目不存在或未绑定所有者"
            )
        return owner_id

    def _existing_project_root(self, root: Path, owner_id: str, project_id: str) -> Path:
        """定位已准备的项目目录；未准备时明确报不存在，不替调用方创建。"""
        project_root = resolve_project_directory(root, owner_id, project_id)
        if not project_root.is_dir():
            raise WorkspaceError(WorkspaceErrorCode.ENTRY_NOT_FOUND, "项目工作区尚未准备")
        return project_root

    # ---------------- 内部：分页与扫描 ----------------

    def _page_size(self, requested: int | None) -> int:
        """校验每页条数：默认取配置值，超出 1~上限 直接拒绝，不做静默截断。"""
        maximum = self.settings.workspace_max_page_size
        size = self.settings.workspace_page_size if requested is None else requested
        if size < 1 or size > maximum:
            raise WorkspaceError(
                WorkspaceErrorCode.INVALID_PATH, f"page_size 必须在 1~{maximum} 之间"
            )
        return size

    def _scan_directory(
        self, directory: int | Path, relative: str
    ) -> tuple[list[FileEntry], str]:
        """扫一层目录，返回排序后的条目和"目录指纹"。

        扫描条目数达到上限时明确报错，不"先无限枚举再截断"。
        指纹只由条目名与类型组成，用于判断分页期间目录是否变化。
        """
        limit = self.settings.workspace_max_scan_entries
        if limit <= 0:
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "目录扫描上限配置无效"
            )
        entries: list[FileEntry] = []
        scanned = 0
        try:
            with os.scandir(directory) as iterator:
                for item in iterator:
                    scanned += 1
                    if scanned > limit:
                        raise WorkspaceError(
                            WorkspaceErrorCode.DIRECTORY_TOO_LARGE,
                            f"目录条目超过服务端上限 {limit}",
                        )
                    entry = self._entry_for(item, relative)
                    if entry is not None:
                        entries.append(entry)
        except OSError as exc:
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "无法读取目录"
            ) from exc

        entries.sort(key=_entry_sort_key)
        fingerprint = hashlib.sha256(
            "\n".join(f"{entry.kind}\x00{entry.name}" for entry in entries).encode("utf-8")
        ).hexdigest()
        return entries, fingerprint

    def _entry_for(self, item: os.DirEntry, relative: str) -> FileEntry | None:
        """把一个目录项转成对外条目；不该出现的类型返回 None。"""
        try:
            # 不跟随链接：符号链接可能指向项目外，一律不作为条目暴露。
            if item.is_symlink():
                return None
            # Windows junction 不一定被 is_symlink 识别，也不能出现在文件树。
            if getattr(item.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400:
                return None
            if item.is_dir(follow_symlinks=False):
                kind, size = ENTRY_KIND_DIRECTORY, None
            elif item.is_file(follow_symlinks=False):
                kind = ENTRY_KIND_FILE
                size = item.stat(follow_symlinks=False).st_size
            else:
                # 设备文件、FIFO、socket 等一律不导出。
                return None
        except OSError:
            # 枚举期间条目被删除或无权限读取元数据：跳过，不让整页失败。
            return None

        child = f"{relative}/{item.name}" if relative else item.name
        if kind == ENTRY_KIND_DIRECTORY:
            if not is_exportable_dir(child):
                return None
        elif not is_exportable(child):
            return None
        return FileEntry(name=item.name, path=child, kind=kind, size_bytes=size)

    # ---------------- 内部：游标 ----------------

    def _cursor_key(self) -> bytes:
        """游标签名密钥：优先用服务令牌，未配置时用进程级随机值。

        随机值意味着进程重启后旧游标自动失效（前端重读第一页），这比接受
        一个跨进程可伪造的游标更安全。没有新增配置项。
        """
        if self._cursor_key_cache is None:
            token = (self.settings.internal_token or "").encode("utf-8")
            self._cursor_key_cache = token or os.urandom(32)
        return self._cursor_key_cache

    def _encode_cursor(
        self, project_id: str, relative: str, offset: int, fingerprint: str
    ) -> str:
        """签发不透明游标：绑定项目、目录、偏移量与目录指纹。"""
        payload = {
            "p": project_id,
            "d": relative,
            "o": offset,
            "f": fingerprint,
            "t": int(time.time()),
        }
        body = _b64url_encode(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )
        signature = hmac.new(
            self._cursor_key(), body.encode("ascii"), hashlib.sha256
        ).digest()[:_CURSOR_MAC_BYTES]
        return f"{body}.{_b64url_encode(signature)}"

    def _decode_cursor(
        self, cursor: str, project_id: str, relative: str
    ) -> tuple[int, str]:
        """校验游标：签名、归属项目、目录、有效期；不合格一律要求重读第一页。"""
        expired = WorkspaceError(
            WorkspaceErrorCode.CURSOR_EXPIRED, "游标无效或已过期，请重新读取第一页"
        )
        try:
            body, _, signature_text = cursor.partition(".")
            if not body or not signature_text:
                raise expired
            expected = hmac.new(
                self._cursor_key(), body.encode("ascii"), hashlib.sha256
            ).digest()[:_CURSOR_MAC_BYTES]
            if not hmac.compare_digest(expected, _b64url_decode(signature_text)):
                raise expired
            payload = json.loads(_b64url_decode(body).decode("utf-8"))
        except WorkspaceError:
            raise
        except (ValueError, binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise expired from exc

        if not isinstance(payload, dict):
            raise expired
        if payload.get("p") != project_id or payload.get("d") != relative:
            # 游标不能当"任意路径"用：它只能续读签发它的那个项目与目录。
            raise expired
        offset = payload.get("o")
        fingerprint = payload.get("f")
        issued_at = payload.get("t")
        if not isinstance(offset, int) or offset < 0:
            raise expired
        if not isinstance(fingerprint, str) or not fingerprint:
            raise expired
        if not isinstance(issued_at, int) or time.time() - issued_at > _CURSOR_TTL_SECONDS:
            raise expired
        return offset, fingerprint
