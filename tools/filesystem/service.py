from fnmatch import fnmatch
from itertools import islice
from pathlib import Path, PurePosixPath, PureWindowsPath

from .FileToolExecutionOutput import ListDirectoryOutput, ReadFileOutput

#此文件用于写具体函数的实现

_IGNORED_DIRECTORIES = {".git", "__pycache__", ".venv", "venv", "target", "node_modules"}
_MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024

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
        raise ValueError("max_depth 必须在 1 到 3 之间")
    if not 1 <= max_entries <= 1000:
        raise ValueError("max_entries 必须在 1 到 1000 之间")

    root = Path(workspace_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("项目工作区不存在或不是目录")

    requested_text = str(directory)
    requested = Path(directory)
    if PurePosixPath(requested_text).is_absolute() or PureWindowsPath(requested_text).is_absolute():
        raise ValueError("directory 必须是工作区内的相对路径")
    if ".." in requested.parts:
        raise ValueError("directory 不能使用 .. 离开当前目录")
    current = root
    for part in requested.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("directory 不能通过符号链接访问目录")
    target = (root / requested).resolve()
    if not target.is_relative_to(root):
        raise ValueError("directory 不能超出工作区")
    if not target.is_dir():
        raise ValueError("directory 不存在或不是目录")

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
        raise ValueError("start_line 必须大于 0")
    if not 1 <= max_lines <= 500:
        raise ValueError("max_lines 必须在 1 到 500 之间")

    root = Path(workspace_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("项目工作区不存在或不是目录")

    requested = Path(file)
    requested_text = str(file)
    windows_path = PureWindowsPath(requested_text)
    if PurePosixPath(requested_text).is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError("file 必须是工作区内的相对路径")
    if ".." in requested.parts:
        raise ValueError("file 不能使用 .. 离开工作区")

    current = root
    for part in requested.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("file 不能通过符号链接访问文件")
    target = (root / requested).resolve()
    if not target.is_relative_to(root):
        raise ValueError("file 不能超出工作区")
    if not target.is_file():
        raise ValueError("file 不存在或不是文件")
    if target.stat().st_size > _MAX_TEXT_FILE_BYTES:
        raise ValueError("文件超过 2 MiB 的读取上限")

    # 多读一行，以便准确判断本次返回是否被 max_lines 截断。
    # 使用通用换行模式，把 Windows 的 CRLF 和 Unix 的 LF 统一为 \n，便于模型阅读。
    with target.open("r", encoding=encoding, newline=None) as stream:
        selected = list(islice(stream, start_line - 1, start_line + max_lines))

    lines = selected[:max_lines]
    return ReadFileOutput(
        path=target.relative_to(root).as_posix(),
        start_line=start_line,
        end_line=start_line + len(lines) - 1 if lines else 0,
        raw="".join(lines),
        content="".join(f"{number}: {line}" for number, line in enumerate(lines, start=start_line)),
        truncated=len(selected) > max_lines,
    )
