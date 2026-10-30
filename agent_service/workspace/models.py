"""工作区对外数据形状，字段名与 Java 说明第 6.1/6.2 节一致。

这些对象只描述"页面需要看到的目录页、文件预览和准备结果"，不持有数据库连接、
不持有打开的文件句柄，也不包含服务器绝对路径。服务层负责把它们序列化成
``data`` 本体交给 Java 包装成 Result。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 目录项只有这两种业务类型；符号链接、设备文件和其它类型一律不对外暴露。
ENTRY_KIND_DIRECTORY = "directory"
ENTRY_KIND_FILE = "file"


@dataclass(frozen=True, slots=True)
class FileEntry:
    """目录页中的一个直接子项。

    ``path`` 是项目内相对路径（``/`` 分隔），前端用它继续浏览或请求预览，
    不是服务器绝对路径；``size_bytes`` 对目录为 ``None``。
    """

    name: str
    path: str
    kind: str
    size_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """转成 Java 说明第 6.1 节示例里的条目字段（四个键，不多不少）。"""

        return {
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class DirectoryPage:
    """一次目录读取的结果页。

    ``next_cursor`` 为 ``None`` 表示本目录已读完；非空时不透明，前端只能原样
    回传，不能自己拼一个路径进来。
    """

    project_id: str
    path: str
    entries: tuple[FileEntry, ...] = field(default_factory=tuple)
    next_cursor: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转成 Java 说明第 6.1 节的 data 本体（条目转为列表）。"""

        return {
            "project_id": self.project_id,
            "path": self.path,
            "entries": [entry.to_dict() for entry in self.entries],
            "next_cursor": self.next_cursor,
        }


@dataclass(frozen=True, slots=True)
class FilePreview:
    """一个允许预览的 UTF-8 文本文件内容。

    ``content`` 是完整内容，不是文件工具默认的行数截断结果；``size_bytes``
    是磁盘真实字节数，超过预览上限时不会构造本对象，而是抛 PREVIEW_TOO_LARGE。
    """

    project_id: str
    path: str
    content: str
    size_bytes: int
    encoding: str = "utf-8"

    def to_dict(self) -> dict[str, Any]:
        """转成 Java 说明第 6.2 节的 data 本体。"""

        return {
            "project_id": self.project_id,
            "path": self.path,
            "content": self.content,
            "size_bytes": self.size_bytes,
            "encoding": self.encoding,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceStatus:
    """准备项目目录后的内部响应；重复调用只会补缺失目录。"""

    project_id: str
    ready: bool = True

    def to_dict(self) -> dict[str, Any]:
        """转成 Java 说明第 8 节表格里约定的 ``{project_id, ready}``。"""

        return {"project_id": self.project_id, "ready": self.ready}
