from tools.registry import ToolDefinition
from functools import partial
from pathlib import Path

from .params import ListDirectoryArgs, ReadTextFileArgs
from .service import list_directory, read_text_file

#把参数模型、描述和实现函数组装成 ToolDefinition


def build_filesystem_tools(
    workspace_root: str | Path,
) -> list[ToolDefinition]:
    """将项目工作区固定在工具实现中，不交给 LLM 决定。"""
    return [
        ToolDefinition(
            name="list_directory",
            description="列出工作区内的目录结构。directory 是相对路径；max_depth 控制层数:层数限制在1~3层；patterns 可选，用于按名称或相对路径筛选。",
            args_model=ListDirectoryArgs,
            function=partial(
                list_directory,
                workspace_root=workspace_root,
            ),
        ),
        ToolDefinition(
            name="read_text_file",
            description="读取工作区内的文本文件。file 是相对路径；start_line 从 1 开始；max_lines 限制返回行数。",
            args_model=ReadTextFileArgs,
            function=partial(read_text_file, workspace_root=workspace_root),
        ),
    ]
