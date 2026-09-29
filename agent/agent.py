from .loop import AgentLoop
from .state import AgentState
from .message import AgentMessage,MessageType

class Agent:
    def __init__(self,loop: AgentLoop) -> None:
        self.loop = loop
        self.state = AgentState()


    async def run(self,prompt:str) -> str:
        message = AgentMessage(
            type=MessageType.USER,
            content=prompt
        )
        self.state.add(message)

        response = await self.loop.run(
            self.state
        )
        #只返回response.output_text是否合理？output里面工具调用在loop里面被执行了
        return response.output_text