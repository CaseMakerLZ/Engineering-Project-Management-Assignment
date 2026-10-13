from tools.registry import ToolDefinition
from functools import partial
from pathlib import Path

from .params import EditTextFileArgs, ListDirectoryArgs, ReadTextFileArgs, SearchTextArgs, WriteTextFileArgs
from .service import edit_text_file, list_directory, read_text_file, search_text, write_text_file

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
        ToolDefinition(
            name="search_text",
            description="在工作区内按普通文本搜索，返回匹配文件、行号和内容；directory 是相对路径，patterns 可筛选文件。",
            args_model=SearchTextArgs,
            function=partial(search_text, workspace_root=workspace_root),
        ),
        ToolDefinition(
            name="write_text_file",
            description="创建 UTF-8 文本文件，或明确允许后完整覆盖；覆盖前可用 expected_sha256 检查文件版本。",
            args_model=WriteTextFileArgs,
            function=partial(write_text_file, workspace_root=workspace_root),
        ),
        ToolDefinition(
            name="edit_text_file",
            description="对已有 UTF-8 文件执行一组精确局部编辑。必须提供最近读取到的 expected_sha256；changes 支持 insert_before、insert_after、replace、delete 和 append。所有修改会先统一校验，再一次性写入。",
            args_model=EditTextFileArgs,
            function=partial(edit_text_file, workspace_root=workspace_root),
        ),
    ]
