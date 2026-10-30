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
import time
from pathlib import Path
from typing import Any

from ..config import Settings
from .exception import WorkspaceError, WorkspaceErrorCode
from .models import (
    ENTRY_KIND_DIRECTORY,
    ENTRY_KIND_FILE,
    DirectoryPage,
    FileEntry,
    WorkspaceStatus,
)
from .policy import (
    ensure_project_directory,
    is_exportable,
    is_exportable_dir,
    is_valid_identifier,
    normalize_path,
    resolve_in_project,
    resolve_project_directory,
)

# 游标有效期：过期必须重读第一页。文档未规定具体时长，取 15 分钟。
_CURSOR_TTL_SECONDS = 900
# 签名截断长度足够防篡改，同时让 URL 不至过长。
_CURSOR_MAC_BYTES = 16


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
        directory = resolve_in_project(project_root, relative)
        if not directory.is_dir():
            raise WorkspaceError(WorkspaceErrorCode.ENTRY_NOT_FOUND, "目录不存在")

        size = self._page_size(page_size)
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

    # ---------------- 内部：路径与归属 ----------------

    def _ensure_cloud_mode(self) -> None:
        """本地模式没有"云端工作区"概念，任何工作区操作都直接拒绝。"""

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
        self, directory: Path, relative: str
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
