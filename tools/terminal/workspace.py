"""隔离副本与安全文件传递；不挂载真实项目，不传播删除，不信任容器的归档路径。"""

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import stat
import tarfile
import tempfile

from agent_service.workspace.policy import is_exportable, is_exportable_dir, open_export_file, open_project_directory
from .exception import TerminalErrorCode, TerminalToolError


@dataclass(frozen=True)
class WorkspaceLimits:
    """传入/传出双向限制，同时限制扫描条数，避免大量空文件耗尽资源。"""
    max_files: int = 1000
    max_bytes: int = 32 * 1024 * 1024
    max_file_bytes: int = 2 * 1024 * 1024

    def __post_init__(self):
        if (isinstance(self.max_files, bool) or not isinstance(self.max_files, int) or not 1 <= self.max_files <= 2000
                or isinstance(self.max_bytes, bool) or not isinstance(self.max_bytes, int) or not 1024 <= self.max_bytes <= 32 * 1024 * 1024
                or isinstance(self.max_file_bytes, bool) or not isinstance(self.max_file_bytes, int)
                or not 1 <= self.max_file_bytes <= self.max_bytes):
            raise ValueError("隔离副本数量/大小配置无效")


def _error(message):
    return TerminalToolError(TerminalErrorCode.WORKSPACE_ERROR, message)


def collect_files(root: Path, limits: WorkspaceLimits) -> dict[str, bytes]:
    """只读取允许的普通文件；持有目录/文件句柄，不沿链接读取宿主内容。"""
    result, scanned, size = {}, 0, 0
    def visit(relative=""):
        nonlocal scanned, size
        with open_project_directory(root, relative) as directory:
            with os.scandir(directory) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > limits.max_files * 4:
                        raise _error("项目条目数量超过隔离副本限制")
                    name = f"{relative}/{entry.name}" if relative else entry.name
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                        raise _error("项目包含链接或重解析点，拒绝复制")
                    if stat.S_ISDIR(info.st_mode):
                        if is_exportable_dir(name):
                            visit(name)
                    elif is_exportable(name):
                        if not stat.S_ISREG(info.st_mode):
                            raise _error("项目包含特殊文件，拒绝复制")
                        stream, info = open_export_file(root, name)
                        with stream:
                            data = stream.read(limits.max_file_bytes + 1)
                        size += len(data)
                        if len(data) > limits.max_file_bytes or size > limits.max_bytes or len(result) >= limits.max_files:
                            raise _error("项目文件数量或大小超过隔离副本限制")
                        result[name] = data
    visit()
    return result


def make_archive(files: dict[str, bytes]) -> bytes:
    """无压缩归档：避免解压炸弹；容器不接触真实路径。"""
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.uid, info.gid = len(data), 0o600, 1000, 1000
            archive.addfile(info, BytesIO(data))
    return output.getvalue()


def read_archive(data: bytes, limits: WorkspaceLimits) -> dict[str, bytes]:
    """不使用extract/extractall；逐项校验后只返回字节，链接/重复/跨平台危险名字直接拒绝。"""
    if len(data) > limits.max_bytes + limits.max_files * 2048 + 10240:
        raise _error("容器归档超过大小限制")
    files, seen, total = {}, set(), 0
    try:
        with tarfile.open(fileobj=BytesIO(data), mode="r:") as archive:
            for index, item in enumerate(archive):
                if index >= limits.max_files * 4:
                    raise _error("容器归档条目过多")
                name = item.name
                parts = name.split("/")
                if (not name or name.startswith("/") or "\\" in name or ":" in name
                        or any(part in {"", ".", ".."} or part.rstrip(" .") != part for part in parts)
                        or any(ord(char) < 32 for char in name) or name.casefold() in seen
                        or any(part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"} for part in parts)):
                    raise _error("容器归档包含非法或重复路径")
                seen.add(name.casefold())
                if not item.isfile() or item.size < 0 or item.size > limits.max_file_bytes:
                    raise _error("容器归档包含链接、特殊文件或超大文件")
                total += item.size
                if total > limits.max_bytes or len(files) >= limits.max_files:
                    raise _error("容器归档文件数量或总大小超限")
                if not is_exportable(name):
                    continue  # 不把.git、凭据、缓存、依赖带回宿主。
                if any("/".join(parts[:index]).casefold() in {key.casefold() for key in files}
                       for index in range(1, len(parts))) or any(key.casefold().startswith(name.casefold() + "/") for key in files):
                    raise _error("容器归档文件与目录路径冲突")
                stream = archive.extractfile(item)
                if stream is None:
                    raise _error("容器归档不完整")
                payload = stream.read(item.size + 1)
                if len(payload) != item.size:
                    raise _error("容器归档不完整")
                files[name] = payload
    except (tarfile.TarError, OSError, ValueError) as exc:
        if isinstance(exc, TerminalToolError):
            raise
        raise _error("容器归档无效，未写回项目") from exc
    return files


def replace_file(root: Path, name: str, data: bytes, expected: bytes | None):
    """固定父目录、比较原版本，再原子替换单文件；不声称多文件事务。"""
    parent, _, leaf = name.rpartition("/")
    with open_project_directory(root, parent, create=True) as directory:
        try:
            stream, _ = open_export_file(root, name)
        except Exception:
            # 仅真正不存在才允许新建；链接、类型异常都不是“不存在”。
            target = root / name
            if target.exists() or target.is_symlink() or expected is not None:
                raise _error("写回文件目标变化或不可安全访问")
            actual = None
        else:
            with stream:
                actual = stream.read(len(expected) + 1 if expected is not None else 1)
        if actual != expected:
            raise TerminalToolError(TerminalErrorCode.WRITE_CONFLICT, "项目文件已被其他操作修改，拒绝覆盖")
        temporary = ".agent-copy-" + os.urandom(12).hex()
        if isinstance(directory, int):
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(data)
                os.replace(temporary, leaf, src_dir_fd=directory, dst_dir_fd=directory)
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
        else:
            target = directory / temporary
            try:
                with target.open("xb") as output:
                    output.write(data)
                os.replace(target, directory / leaf)
            finally:
                target.unlink(missing_ok=True)


class SandboxWorkspace:
    """每项任务一个私有副本；文件工具与容器共用副本，结束后受控写回。"""
    def __init__(self, project: Path, limits: WorkspaceLimits):
        self.project, self.limits = project, limits
        self._temporary = tempfile.TemporaryDirectory(prefix="agent-isolated-")
        self.root = Path(self._temporary.name) / "project"
        self.root.mkdir()
        try:
            self.original = collect_files(project, limits)
            for name, data in self.original.items():
                replace_file(self.root, name, data, None)
        except BaseException:
            self.close()
            raise

    def apply(self, files: dict[str, bytes]):
        """命令结束后更新副本；容器中的删除不传播，后续文件工具能看到命令生成的文件。"""
        before = collect_files(self.root, self.limits)
        merged = {**before, **files}
        if len(merged) > self.limits.max_files or sum(len(data) for data in merged.values()) > self.limits.max_bytes:
            raise _error("保留删除文件后的副本总量超限，未接收本次产物")
        for name, data in files.items():
            if before.get(name) != data:
                replace_file(self.root, name, data, before.get(name))

    def publish(self) -> dict:
        """先检查全部产物；冲突不覆盖，部分写回要返回清单，失败任务也保留合格文件。"""
        after = collect_files(self.root, self.limits)
        changed = {name: data for name, data in after.items() if self.original.get(name) != data}
        written, failed = [], []
        for name, data in changed.items():
            try:
                replace_file(self.project, name, data, self.original.get(name))
                written.append(name)
            except Exception:
                failed.append(name)
        return {"written": written, "failed": failed,
                "deletions_not_applied": sorted(set(self.original) - set(after))}

    def close(self):
        """只清理由TemporaryDirectory创建的精确目录，不接受模型路径。"""
        self._temporary.cleanup()
