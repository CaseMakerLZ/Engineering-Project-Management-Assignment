"""在 Agent 开始运行前组装一份上下文快照。

这个模块只负责上下文的顺序和内容边界，不负责：

* 调用 LLM；
* 执行记忆工具；
* 查询 Java 的 ``agent_task``；
* 判断文本相似度或自动寻找“最相关”的历史；
* 修改数据库。

历史数据由 RunRepository 提供，仓储的 SQLite/MySQL 差异留在仓储实现内部。
这样上下文规则只需要维护一份，也不会影响 Java 对外的 B7～B9 接口。
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from agent.message import AgentMessage, MessageType
from agent_service.domain import Run


class HistoryRepository(Protocol):
    """ContextBuilder 实际需要的最小历史查询能力。

    这里使用结构化的 Protocol，而不是依赖具体的 SQLite 或 MySQL 类。
    这样 Builder 不需要知道数据库类型，也方便用一个很小的假仓储测试。
    """

    def list_recent_completed_runs(
        self, project_id: str, conversation_id: str, before_created_at: datetime, limit: int
    ) -> list[Run]:
        """
        返回当前运行之前的历史运行。

        具体的“同项目、同对话、已完成、数量限制、时间顺序”由仓储保证；
        Builder 不再重复写 SQL 条件，避免两层各自实现一套筛选规则。
        """


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    """本轮 Agent 启动时实际准备好的上下文内容。

    ``system_prompt`` 现在故意是空字符串。系统提示词以后会加入这里，
    但当前不提前假设它的具体文本，也不把项目说明冒充成系统提示词。

    ``project_instructions`` 是项目目录中的 AGENTS.md 内容；文件不存在时
    为 None。它是项目规则，不属于长期记忆，也不会被 search_memory 搜索。

    ``messages`` 只包含最近已完成轮次的 user/assistant 消息；当前轮用户
    prompt 由 Agent.run() 在后面追加，因此 Builder 不会重复添加当前 prompt。
    """

    system_prompt: str
    project_instructions: str | None
    messages: tuple[AgentMessage, ...]


class ContextBuilder:
    """根据项目说明和近期运行历史生成初始上下文。

    第一版使用固定的最近历史窗口，而不是关键词匹配或额外的记忆规划请求。
    如果 Agent 需要更久以前的材料，未来由 search_memory 在 AgentLoop 中按需
    回溯；那不是启动时 ContextBuilder 的职责。
    """

    def __init__(self, repository: HistoryRepository, *, max_history_turns: int = 10) -> None:
        if max_history_turns < 0:
            raise ValueError("max_history_turns 不能小于 0")
        self.repository = repository
        self.max_history_turns = max_history_turns

    def build(
        self,
        *,
        project_id: str,
        conversation_id: str | None,
        current_created_at: datetime,
        project_root: str | Path,
    ) -> ContextSnapshot:
        """生成一次独立的启动快照。

        参数中的 current_created_at 应来自当前 agent_run.created_at，而不是
        使用“现在”重新查询。这样即使数据库中已有更晚创建的任务，也不会把
        当前运行之后的记录错误地放进当前上下文。
        """
        project_instructions = self._read_project_instructions(project_root)

        # 系统提示词预留位置：后续可在这里放全局 Agent 规则，但目前保持为空。
        system_prompt = ""

        # 没有对话 ID 的单次运行仍可读取 AGENTS.md，但没有可归属的对话历史。
        if self.max_history_turns == 0 or conversation_id is None:
            history: list[Run] = []
        else:
            history = self.repository.list_recent_completed_runs(
                project_id,
                conversation_id,
                current_created_at,
                self.max_history_turns,
            )

        # 历史运行只转换为 user/assistant 两类消息。
        # 工具过程不会在每次启动时全部复制；需要时由未来的 search_memory 回溯。
        messages: list[AgentMessage] = []
        for run in history:
            messages.append(AgentMessage(type=MessageType.USER, content=run.prompt))
            if run.result is not None and run.result.strip():
                messages.append(AgentMessage(type=MessageType.ASSISTANT, content=run.result))

        return ContextSnapshot(
            system_prompt=system_prompt,
            project_instructions=project_instructions,
            messages=tuple(messages),
        )

    @staticmethod
    def _read_project_instructions(project_root: str | Path) -> str | None:
        """读取项目自己的 AGENTS.md；没有文件时不注入任何项目说明。

        项目说明来自当前受服务端约束的 project_root，而不是模型提供的路径。
        这里不递归读取父目录的 AGENTS.md，避免把另一个项目的规则带入当前任务。
        文件读取失败时直接抛出异常，让上层决定如何报告配置问题；不能静默地
        假装项目说明不存在。
        """
        instructions_path = Path(project_root).expanduser().resolve() / "AGENTS.md"
        if not instructions_path.is_file():
            return None
        content = instructions_path.read_text(encoding="utf-8")
        return content if content.strip() else None
