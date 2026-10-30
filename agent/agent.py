from .loop import AgentLoop
from .state import AgentState
from .message import AgentMessage,MessageType
from typing import Callable
from tools.executor import ToolExecutionResult

class Agent:
    def __init__(self,loop: AgentLoop) -> None:
        self.loop = loop
        self.state = AgentState()


    async def run(
        self, prompt: str, *, on_text: Callable[[str, str], None] | None = None,
        on_tool_started: Callable[[str, str], None] | None = None,
        on_tool_finished: Callable[[str, str, ToolExecutionResult], None] | None = None,
    ) -> str:
        message = AgentMessage(
            type=MessageType.USER,
            content=prompt
        )
        self.state.add(message)

        response = await self.loop.run(
            self.state,
            on_text=on_text,
            on_tool_started=on_tool_started,
            on_tool_finished=on_tool_finished,
        )
        #只返回response.output_text是否合理？output里面工具调用在loop里面被执行了
        return response.output_text
