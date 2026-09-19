from .state import AgentState
from llm.client import LLMClient#报错了

class Agent:
    def __init__(self,llm:LLMClient) -> None:
        self.llm = llm
        self.state = AgentState()


    async def run(self,prompt:str) -> str:
        self.state.add({
            "type": "message",
            "role": "user",
            "content": prompt
        })

        response = await self.llm.generate(
            self.state.get_history()
        )

        self.state.add(response.output)
        return response.output_text