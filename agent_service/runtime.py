#这个文件是整个 agent_service 与现有 Agent Core 之间的适配器。
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
    # Runtime 同时返回最终答案和运行过程中产生的消息，供任务表与消息表分别保存。
    result: str
    messages: list[AgentMessage]


class AgentRuntime(Protocol):
    '''
    继承Protocol，本类是一个协议类
    函数只声明签名，不提供实现，“...”作为占位符
    '''
    async def run(self, prompt: str, project_id: str | None = None) -> RuntimeResult:
        ...


class CurrentAgentRuntime:
    """Adapter around the current handwritten Agent Core."""
    # 这是当前第一版实现；未来可以新增 LangGraphRuntime，而不修改 RunService。
    #这个run是AgentRuntime.run的,组装Agent并加入提示词进行Agent运行
    async def run(self, prompt: str, project_id: str | None = None) -> RuntimeResult:
        del project_id
        llm = LLMClient()
        registry = ToolRegistry()
        executor = ToolExecutor(registry)
        loop = AgentLoop(llm, registry, executor)
        agent = Agent(loop)
        result = await agent.run(prompt)
        return RuntimeResult(result=result, messages=agent.state.get_history())

#把内部 Agent 消息转换成可持久化的二元组，eg:("assistant", {...})
def serialize_message(message: AgentMessage) -> tuple[str, Any]:
    # 持久化边界只接受消息类型和值，不把 AgentMessage 对象直接写入数据库。
    return message.type.value, message.content
