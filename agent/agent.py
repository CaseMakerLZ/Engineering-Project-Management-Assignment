from .loop import AgentLoop
from .state import AgentState

class Agent:
    def __init__(self,loop: AgentLoop) -> None:
        self.loop = loop
        self.state = AgentState()


    async def run(self,prompt:str) -> str:
        self.state.add({
            "type": "message",
            "role": "user",
            "content": prompt
        })

        response = await self.loop.run(
            self.state
        )

        return response.output_text