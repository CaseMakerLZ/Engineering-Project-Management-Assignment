from fnmatch import fnmatch
from hashlib import sha256
from io import BytesIO, TextIOWrapper
from itertools import islice
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import tempfile
from dataclasses import dataclass

from .FileToolExecutionOutput import (
    EditFileOutput,
    ListDirectoryOutput,
    ReadFileOutput,
    SearchTextOutput,
    WriteFileOutput,
)
from .exception import FilesystemErrorCode, FilesystemToolError

#此文件用于写具体函数的实现

#这些到时候也可以写入配置文件而非写在此
_IGNORED_DIRECTORIES = {".git", "__pycache__", ".venv", "venv", "target", "node_modules"}
_MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024
_MAX_SEARCHED_FILES = 1000
_MAX_SEARCHED_BYTES = 32 * 1024 * 1024
_MAX_MATCH_LINE_CHARS = 500


def _raise_fs(code: FilesystemErrorCode, message: str, *, cause: BaseException | None = None) -> None:
    """用统一的文件工具异常抛出失败；具体原因由错误码表达。"""
    raise FilesystemToolError(code, message, cause=cause)

'''
e.g:

{
  "path": "tools",
  "entries": [
    {"path": "tools/filesystem", "kind": "directory"},
    {"path": "tools/bootstrap.py", "kind": "file"}
  ],
  "returned_count": 2,
  "truncated": false
}
'''
def list_directory(
    directory: Path = Path("."),
    max_depth: int = 1,
    max_entries: int = 150,
    patterns: list[str] | None = None,
    *,
    workspace_root: str | Path,
) -> ListDirectoryOutput:
    """列出项目工作区内的文件和目录；workspace_root 已由 bootstrap 选定。"""
    if not 1 <= max_depth <= 3:
        _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "max_depth 必须在 1 到 3 之间")
    if not 1 <= max_entries <= 1000:
        _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "max_entries 必须在 1 到 1000 之间")

    root = Path(workspace_root).expanduser().resolve()
    if not root.is_dir():
        _raise_fs(FilesystemErrorCode.CONFIGURATION_ERROR, "项目工作区不存在或不是目录")

    requested_text = str(directory)
    requested = Path(directory)
    if PurePosixPath(requested_text).is_absolute() or PureWindowsPath(requested_text).is_absolute():
        _raise_fs(FilesystemErrorCode.PATH_BOUNDARY, "directory 必须是工作区内的相对路径")
    if ".." in requested.parts:
        _raise_fs(FilesystemErrorCode.PATH_BOUNDARY, "directory 不能使用 .. 离开当前目录")
    current = root
    for part in requested.parts:
        current = current / part
        if current.is_symlink():
            _raise_fs(FilesystemErrorCode.PATH_BOUNDARY, "directory 不能通过符号链接访问目录")
    target = (root / requested).resolve()
    if not target.is_relative_to(root):
        _raise_fs(FilesystemErrorCode.PATH_BOUNDARY, "directory 不能超出工作区")
    if not target.is_dir():
        _raise_fs(FilesystemErrorCode.WRONG_TARGET_TYPE, "directory 不存在或不是目录")

    entries: list[dict[str, str]] = []

    def visit(current: Path, depth: int) -> None:
        # 排序保证目录先于文件，且相同目录每次返回相同的顺序。
        children = sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
        for child in children:
            # 不能沿符号链接离开工作区；忽略构建产物和缓存目录。
            if child.is_symlink() or (child.is_dir() and child.name in _IGNORED_DIRECTORIES):
                continue
            relative_path = child.relative_to(root).as_posix()
            matches = not patterns or any(
                fnmatch(child.name, pattern) or fnmatch(relative_path, pattern)
                for pattern in patterns
            )
            if matches:
                # 多找一条才知道结果是否真的被截断。
                entries.append({"path": relative_path, "kind": "directory" if child.is_dir() else "file"})
                if len(entries) > max_entries:
                    return
            if child.is_dir() and depth < max_depth:
                visit(child, depth + 1)
                if len(entries) > max_entries:
                    return

    visit(target, 1)
    return ListDirectoryOutput(
        path="." if target == root else target.relative_to(root).as_posix(),
        entries=entries[:max_entries],
        returned_count=min(len(entries), max_entries),
        truncated=len(entries) > max_entries,
    )


def read_text_file(
    file: Path,
    start_line: int = 1,
    max_lines: int = 200,
    encoding: str = "utf-8",
    *,
    workspace_root: str | Path,
) -> ReadFileOutput:
    """读取项目内文本文件的指定行，返回原文和带行号的展示内容。"""
    if start_line < 1:
        _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "start_line 必须大于 0")
    if not 1 <= max_lines <= 500:
        _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "max_lines 必须在 1 到 500 之间")

    root = Path(workspace_root).expanduser().resolve()
    if not root.is_dir():
        _raise_fs(FilesystemErrorCode.CONFIGURATION_ERROR, "项目工作区不存在或不是目录")

    requested = Path(file)
    requested_text = str(file)
    windows_path = PureWindowsPath(requested_text)
    if PurePosixPath(requested_text).is_absolute() or windows_path.is_absolute() or windows_path.drive:
        _raise_fs(FilesystemErrorCode.PATH_BOUNDARY, "file 必须是工作区内的相对路径")
    if ".." in requested.parts:
        _raise_fs(FilesystemErrorCode.PATH_BOUNDARY, "file 不能使用 .. 离开工作区")

    current = root
    for part in requested.parts:
        current = current / part
        if current.is_symlink():
            _raise_fs(FilesystemErrorCode.PATH_BOUNDARY, "file 不能通过符号链接访问文件")
    target = (root / requested).resolve()
    if not target.is_relative_to(root):
        _raise_fs(FilesystemErrorCode.PATH_BOUNDARY, "file 不能超出工作区")
    if not target.is_file():
        _raise_fs(FilesystemErrorCode.NOT_FOUND, "file 不存在或不是文件")
    if target.stat().st_size > _MAX_TEXT_FILE_BYTES:
        _raise_fs(FilesystemErrorCode.RESOURCE_LIMIT, "文件超过 2 MiB 的读取上限")

    # 文本和哈希来自同一份文件字节，避免两次读取之间发生修改而得到错误的版本号。
    data = target.read_bytes()
    if len(data) > _MAX_TEXT_FILE_BYTES:
        _raise_fs(FilesystemErrorCode.RESOURCE_LIMIT, "文件超过 2 MiB 的读取上限")
    # 多读一行判断截断；通用换行模式会把 CRLF 和 LF 统一为 \n。
    with TextIOWrapper(BytesIO(data), encoding=encoding, newline=None) as stream:
        selected = list(islice(stream, start_line - 1, start_line + max_lines))

    lines = selected[:max_lines]
    return ReadFileOutput(
        path=target.relative_to(root).as_posix(),
        start_line=start_line,
        end_line=start_line + len(lines) - 1 if lines else 0,
        raw="".join(lines),
        content="".join(f"{number}: {line}" for number, line in enumerate(lines, start=start_line)),
        truncated=len(selected) > max_lines,
        sha256=sha256(data).hexdigest(),
    )


def _project_path(workspace_root: str | Path, relative: str | Path, *, is_file: bool) -> tuple[Path, Path]:
    """把模型给的路径限制在已选定的项目工作区内。"""
    root = Path(workspace_root).expanduser().resolve()
    if not root.is_dir():
        _raise_fs(FilesystemErrorCode.CONFIGURATION_ERROR, "项目工作区不存在或不是目录")

    text = str(relative)
    windows_path = PureWindowsPath(text)
    if not text.strip() or PurePosixPath(text).is_absolute() or windows_path.drive or windows_path.root:
        _raise_fs(FilesystemErrorCode.PATH_BOUNDARY, "路径必须是项目工作区内的相对路径")
    # Pydantic 的 Path 在 Windows 上会显示为反斜杠；两种分隔符在各平台统一解析。
    requested = Path(*PurePosixPath(text.replace("\\", "/")).parts)
    if ".." in requested.parts:
        _raise_fs(FilesystemErrorCode.PATH_BOUNDARY, "路径不能使用 .. 离开工作区")
    if is_file and requested == Path("."):
        _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "必须指定文件路径")
    if any(part in _IGNORED_DIRECTORIES for part in requested.parts):
        _raise_fs(FilesystemErrorCode.PROTECTED_PATH, "不能访问受保护的项目目录")

    current = root
    for part in requested.parts:
        current = current / part
        if current.is_symlink():
            _raise_fs(FilesystemErrorCode.PATH_BOUNDARY, "不能通过符号链接访问项目文件")
    target = (root / requested).resolve()
    if not target.is_relative_to(root):
        _raise_fs(FilesystemErrorCode.PATH_BOUNDARY, "路径不能超出项目工作区")
    return root, target


def search_text(
    query: str,
    directory: Path = Path("."),
    patterns: list[str] | None = None,
    case_sensitive: bool = False,
    max_results: int = 100,
    *,
    workspace_root: str | Path,
) -> SearchTextOutput:
    """在项目文本文件中按字面内容查找，返回有界的行级匹配。"""
    if not query.strip() or len(query) > 256 or not 1 <= max_results <= 500:
        _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "query 必须为 1 到 256 个字符，max_results 必须在 1 到 500 之间")
    root, target = _project_path(workspace_root, directory, is_file=False)
    if not target.is_dir():
        _raise_fs(FilesystemErrorCode.WRONG_TARGET_TYPE, "directory 不存在或不是目录")

    matches: list[dict[str, str | int | bool]] = []
    skipped_files = scanned_files = scanned_bytes = 0
    truncated = False
    needle = query if case_sensitive else query.casefold()

    for current, dirs, files in os.walk(target, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(d for d in dirs if d not in _IGNORED_DIRECTORIES and not (current_path / d).is_symlink())
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink():
                skipped_files += 1
                continue
            relative_path = path.relative_to(root).as_posix()
            if patterns and not any(fnmatch(name, pattern) or fnmatch(relative_path, pattern) for pattern in patterns):
                continue
            if scanned_files >= _MAX_SEARCHED_FILES:
                truncated = True
                break
            try:
                size = path.stat().st_size
                if size > _MAX_TEXT_FILE_BYTES:
                    skipped_files += 1
                    continue
                if scanned_bytes + size > _MAX_SEARCHED_BYTES:
                    truncated = True
                    break
                scanned_files += 1
                scanned_bytes += size
                content = path.read_text(encoding="utf-8")
                if "\x00" in content:
                    skipped_files += 1
                    continue
            except (OSError, UnicodeError):
                skipped_files += 1
                continue

            for line_number, line in enumerate(content.splitlines(), start=1):
                haystack = line if case_sensitive else line.casefold()
                if needle not in haystack:
                    continue
                if len(matches) == max_results:
                    truncated = True
                    break
                # 长行只返回局部，但片段必须包含第一次命中的位置。
                match_at = haystack.find(needle)
                snippet_start = max(0, min(match_at - 100, len(line) - _MAX_MATCH_LINE_CHARS))
                matches.append({
                    "path": relative_path,
                    "line": line_number,
                    "content": line[snippet_start:snippet_start + _MAX_MATCH_LINE_CHARS],
                    "line_truncated": len(line) > _MAX_MATCH_LINE_CHARS,
                })
            if truncated:
                break
        if truncated:
            break

    return SearchTextOutput(
        query=query, matches=matches, returned_count=len(matches),
        truncated=truncated, skipped_files=skipped_files,
    )


def _check_expected_hash(data: bytes, expected_sha256: str | None) -> None:
    if expected_sha256 is not None and sha256(data).hexdigest() != expected_sha256.lower():
        _raise_fs(FilesystemErrorCode.VERSION_CONFLICT, "文件已变化，请重新读取后再修改")


def _atomic_write(target: Path, data: bytes, *, overwrite: bool) -> None:
    """临时文件位于同一目录；新建时使用独占硬链接，避免覆盖竞态。"""
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent, prefix=".agent-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            shutil.copymode(target, temporary)
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_text_file(
    file: Path,
    content: str,
    overwrite: bool = False,
    create_parents: bool = True,
    expected_sha256: str | None = None,
    *,
    workspace_root: str | Path,
) -> WriteFileOutput:
    """新建或完整覆盖 UTF-8 文件；默认拒绝覆盖已有文件。"""
    root, target = _project_path(workspace_root, file, is_file=True)
    data = content.encode("utf-8")
    if len(data) > _MAX_TEXT_FILE_BYTES or "\x00" in content:
        _raise_fs(FilesystemErrorCode.CONTENT_UNSUPPORTED, "内容不是受支持的文本或超过 2 MiB 写入上限")
    if expected_sha256 is not None and not target.exists():
        _raise_fs(FilesystemErrorCode.NOT_FOUND, "指定了 expected_sha256，但目标文件不存在")
    if not target.parent.is_dir():
        if not create_parents:
            _raise_fs(FilesystemErrorCode.NOT_FOUND, "父目录不存在")
        target.parent.mkdir(parents=True, exist_ok=True)
        # 创建父目录后再次检查，避免中途出现符号链接。
        root, target = _project_path(workspace_root, file, is_file=True)
    if not target.parent.is_dir():
        _raise_fs(FilesystemErrorCode.WRONG_TARGET_TYPE, "父路径不是目录")

    exists = target.exists()
    if exists:
        if not target.is_file() or not overwrite:
            _raise_fs(FilesystemErrorCode.WRITE_CONFLICT, "文件已存在且未允许覆盖，或目标不是普通文件")
        original = target.read_bytes()
        _check_expected_hash(original, expected_sha256)
    _atomic_write(target, data, overwrite=exists)
    return WriteFileOutput(
        path=target.relative_to(root).as_posix(), created=not exists,
        overwritten=exists, bytes_written=len(data), sha256=sha256(data).hexdigest(),
    )


@dataclass(frozen=True)
class _ResolvedEdit:
    """一项编辑在原文件中的位置和替换文本。"""

    start: int
    end: int
    replacement: str


def _all_occurrences(text: str, needle: str) -> list[int]:
    """查找所有匹配，包括相互重叠的匹配。"""
    if not needle:
        return []
    positions: list[int] = []
    offset = 0
    while True:
        position = text.find(needle, offset)
        if position < 0:
            return positions
        positions.append(position)
        offset = position + 1


def _unique_occurrence(text: str, value: str, field_name: str) -> tuple[int, int]:
    positions = _all_occurrences(text, value)
    if len(positions) != 1:
        _raise_fs(FilesystemErrorCode.WRITE_CONFLICT, f"{field_name} 必须在文件中恰好出现一次，实际为 {len(positions)} 次")
    start = positions[0]
    return start, start + len(value)


def _edits_conflict(left: _ResolvedEdit, right: _ResolvedEdit) -> bool:
    """判断两项编辑是否会争用同一个原文件位置。"""
    # 两个插入点相同，无法在不依赖数组顺序的情况下确定结果。
    if left.start == left.end and right.start == right.end:
        return left.start == right.start
    # 插入点落在替换范围的边界也视为冲突，避免“先插入还是先替换”的歧义。
    if left.start == left.end:
        return right.start <= left.start <= right.end
    if right.start == right.end:
        return left.start <= right.start <= left.end
    return left.start < right.end and right.start < left.end


def _resolve_edit(change: dict, text: str) -> _ResolvedEdit:
    operation = change.get("operation")
    if operation == "insert_before":
        start, _ = _unique_occurrence(text, change["anchor"], "anchor")
        return _ResolvedEdit(start, start, change["content"])
    if operation == "insert_after":
        _, end = _unique_occurrence(text, change["anchor"], "anchor")
        return _ResolvedEdit(end, end, change["content"])
    if operation == "replace":
        start, end = _unique_occurrence(text, change["old_text"], "old_text")
        return _ResolvedEdit(start, end, change["new_text"])
    if operation == "delete":
        start, end = _unique_occurrence(text, change["old_text"], "old_text")
        return _ResolvedEdit(start, end, "")
    if operation == "append":
        return _ResolvedEdit(len(text), len(text), change["content"])
    _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "不支持的编辑操作")


def edit_text_file(
    file: Path,
    expected_sha256: str,
    changes: list[dict],
    *,
    workspace_root: str | Path,
) -> EditFileOutput:
    """在同一份原文件上校验并应用一组局部编辑，成功后只写回一次。"""
    root, target = _project_path(workspace_root, file, is_file=True)
    if not target.is_file() or not changes:
        _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "目标必须是已有文件，changes 不能为空")
    original = target.read_bytes()
    if len(original) > _MAX_TEXT_FILE_BYTES:
        _raise_fs(FilesystemErrorCode.RESOURCE_LIMIT, "文件超过 2 MiB 编辑上限")
    if b"\x00" in original:
        _raise_fs(FilesystemErrorCode.CONTENT_UNSUPPORTED, "不能编辑二进制文件")
    _check_expected_hash(original, expected_sha256)
    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FilesystemToolError(
            FilesystemErrorCode.CONTENT_UNSUPPORTED,
            "文件不是有效的 UTF-8 文本",
            cause=exc,
        ) from exc

    resolved: list[_ResolvedEdit] = []
    for change in changes:
        if not isinstance(change, dict):
            _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "每项 changes 必须是对象")
        operation = change.get("operation")
        if operation in {"insert_before", "insert_after"}:
            if not isinstance(change.get("anchor"), str) or not change["anchor"]:
                _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "插入操作的 anchor 不能为空")
            if not isinstance(change.get("content"), str):
                _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "插入操作的 content 必须是文本")
        elif operation == "replace":
            if not isinstance(change.get("old_text"), str) or not change["old_text"]:
                _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "replace 操作的 old_text 不能为空")
            if not isinstance(change.get("new_text"), str):
                _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "replace 操作的 new_text 必须是文本")
        elif operation == "delete":
            if not isinstance(change.get("old_text"), str) or not change["old_text"]:
                _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "delete 操作的 old_text 不能为空")
        elif operation == "append":
            if not isinstance(change.get("content"), str):
                _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "append 操作的 content 必须是文本")
        else:
            _raise_fs(FilesystemErrorCode.INVALID_ARGUMENT, "不支持的编辑操作")

        values = [value for key, value in change.items() if key in {"anchor", "old_text", "new_text", "content"}]
        if any("\x00" in value for value in values):
            _raise_fs(FilesystemErrorCode.CONTENT_UNSUPPORTED, "编辑内容不能包含 NUL 字符")
        resolved.append(_resolve_edit(change, text))

    for index, current in enumerate(resolved):
        if any(_edits_conflict(current, other) for other in resolved[index + 1:]):
            _raise_fs(FilesystemErrorCode.WRITE_CONFLICT, "changes 中存在重叠或冲突的修改")

    # 从后往前替换，前面位置的坐标不会因后面的修改而变化。
    updated = text
    for edit in sorted(resolved, key=lambda item: (item.start, item.end), reverse=True):
        updated = updated[:edit.start] + edit.replacement + updated[edit.end:]
    data = updated.encode("utf-8")
    if len(data) > _MAX_TEXT_FILE_BYTES:
        _raise_fs(FilesystemErrorCode.RESOURCE_LIMIT, "修改后文件超过 2 MiB 写入上限")

    _atomic_write(target, data, overwrite=True)
    return EditFileOutput(
        path=target.relative_to(root).as_posix(), applied_changes=len(resolved),
        bytes_written=len(data), sha256=sha256(data).hexdigest(),
    )
