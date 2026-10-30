"""记忆工具的注册定义。"""

from datetime import datetime
from functools import partial
from typing import Any

from tools.registry import ToolDefinition

from .params import RememberArgs, SearchMemoryArgs
from agent_service.storage.repository import MemoryRepository

from .service import remember, search_memory


def build_memory_tools(
    *,
    repository: MemoryRepository,
    project_id: str,
    conversation_id: str | None,
    before_created_at: datetime,
    run_id: str,
) -> list[ToolDefinition]:
    """把运行边界绑定到工具实现，再交给模型填写业务参数。"""
    tools = [
        ToolDefinition(
            name="search_memory",
            description=(
                "在当前项目、当前对话的历史运行中进行回忆。默认查询最近一周，"
                "返回历史问题和最终结果；只有明确需要事件回溯时才设置 include_process=true。"
                "fuzzy_match=true 时才启用受控文本匹配，它不是语义相似度检索。"
            ),
            args_model=SearchMemoryArgs,
            function=partial(
                search_memory,
                repository=repository,
                project_id=project_id,
                conversation_id=conversation_id,
                before_created_at=before_created_at,
            ),
        ),
        ToolDefinition(
            name="remember",
            description=(
                "保存当前轮已经明确确认、未来可能需要复用的一条长期记忆。"
                "不要把普通过程消息、临时猜测或未经确认的内容写入长期记忆。"
                "记忆在当前项目的各个对话间共享，下次运行会自动读取。"
                "新建时省略 memory_id；修改已有记忆时填写上下文中对应的 memory_id，"
                "并提交完整的新内容。未知 ID 会报错，不会新建。"
            ),
            args_model=RememberArgs,
            function=partial(
                remember,
                repository=repository,
                project_id=project_id,
                source_run_id=run_id,
            ),
        ),
    ]
    # 历史回溯仍以对话为边界；没有对话时只开放项目级 remember。
    return tools if conversation_id is not None else tools[1:]
