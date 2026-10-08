'''
这个类负责：

创建 ToolRegistry
    ↓
注册 filesystem 工具(finished)
    ↓
注册 web 工具
    ↓
注册 terminal 工具
    ↓
返回完整的 ToolRegistry
'''
from pathlib import Path
import re

from tools.filesystem.definitions import build_filesystem_tools
from tools.registry import ToolRegistry


def create_default_registry(
    workspace_root: str | Path | None = None,
    project_id: str | None = None,
) -> ToolRegistry:
    """创建绑定到一个项目目录的工具注册表。

    workspace_root 是所有项目目录的父目录；project_id 对应其中一个子目录。
    """
    root = Path(workspace_root) if workspace_root is not None else Path.cwd()
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("工作区根目录不存在或不是目录")

    if project_id is not None:
        # Java 当前使用 UUID。限制为可移植的单层目录名，避免 Windows/Linux 路径解释不同。
        if not re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
            raise ValueError("project_id 只能包含字母、数字、下划线和连字符")
        project_path = root / project_id
        if project_path.is_symlink():
            raise ValueError("项目工作区不能是符号链接")
        project_root = project_path.resolve()
        if not project_root.is_relative_to(root) or not project_root.is_dir():
            raise ValueError("项目工作区不存在或不在工作区根目录内")
    else:
        # 本地调试模式：未指定 project_id 时，workspace_root 本身是当前工作区。
        project_root = root

    registry = ToolRegistry()
    for tool in build_filesystem_tools(project_root):
        registry.register(tool)
    return registry
