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

        return response.output_text