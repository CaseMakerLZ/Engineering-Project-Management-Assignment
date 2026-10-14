# 这个文件把正式 HTTP 服务连接到现有的 Agent Core。
from dataclasses import dataclass
from typing import Protocol

from agent.agent import Agent
from agent.loop import AgentLoop
from agent.message import AgentMessage, MessageType
from llm.client import LLMClient
from tools.executor import ToolExecutor
from tools.bootstrap import create_default_registry


@dataclass(slots=True)
class RuntimeResult:
    # Agent 执行结束后返回最终回答和本次运行的过程消息。
    result: str
    messages: list[AgentMessage]


class AgentRuntime(Protocol):
    """所有 Agent 运行方式都需要提供的统一调用方法。"""
    async def run(self, prompt: str, project_id: str | None = None, context: list[dict[str, str]] | None = None) -> RuntimeResult:
        ...


class CurrentAgentRuntime:
    """使用当前手写 Agent Core 执行任务。"""

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = workspace_root

    # 以后替换 Agent 实现时，只需要增加新的 Runtime，不用修改任务服务。
    async def run(self, prompt: str, project_id: str | None = None, context: list[dict[str, str]] | None = None) -> RuntimeResult:
        llm = LLMClient()
        registry = create_default_registry(
            workspace_root=self.workspace_root,
            project_id=project_id,
        )
        executor = ToolExecutor(registry)
        loop = AgentLoop(llm, registry, executor)
        agent = Agent(loop)
        for message in context or []:
            message_type = MessageType.USER if message["role"] == "user" else MessageType.ASSISTANT
            agent.state.add(AgentMessage(type=message_type, content=message["content"]))
        result = await agent.run(prompt)
        # 历史消息只帮助本轮回答，不重复保存为本轮新消息。
        return RuntimeResult(result=result, messages=agent.state.get_history()[len(context or []):])
