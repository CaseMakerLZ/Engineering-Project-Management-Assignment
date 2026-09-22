from dataclasses import dataclass
from typing import Any, Protocol

from agent.agent import Agent
from agent.loop import AgentLoop
from agent.message import AgentMessage
from llm.client import LLMClient
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry


@dataclass(slots=True)
class RuntimeResult:
    result: str
    messages: list[AgentMessage]


class AgentRuntime(Protocol):
    async def run(self, prompt: str, project_id: str | None = None) -> RuntimeResult:
        ...


class CurrentAgentRuntime:
    """Adapter around the current handwritten Agent Core."""

    async def run(self, prompt: str, project_id: str | None = None) -> RuntimeResult:
        del project_id
        llm = LLMClient()
        registry = ToolRegistry()
        executor = ToolExecutor(registry)
        loop = AgentLoop(llm, registry, executor)
        agent = Agent(loop)
        result = await agent.run(prompt)
        return RuntimeResult(result=result, messages=agent.state.get_history())


def serialize_message(message: AgentMessage) -> tuple[str, Any]:
    return message.type.value, message.content

