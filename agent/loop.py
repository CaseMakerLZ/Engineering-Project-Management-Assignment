from agent.state import AgentStatus
from llm.client import LLMClient
from typing import Any
from tools.executor import ToolExecutor, ToolExecutionResult
from tools.registry import ToolRegistry
from .state import AgentState

class AgentLoop:
    def __init__(self,
                 llm: LLMClient,
                 registry: ToolRegistry,
                 executor: ToolExecutor) -> None:
        self.client : LLMClient = llm
        self.executor : ToolExecutor = executor
        self.registry: ToolRegistry = registry

    async def run(self,state: AgentState) -> Any:
        state.status = AgentStatus.RUNNING
        while True:

            if not state.can_continue():
                state.status = AgentStatus.MAX_STEPS_EXCEEDED
                return None

            state.increment_step()
            print(f"第{state.step}次循环")

            response = await self.client.generate(
                input=state.get_history(),
                tools=self.registry.get_llm_tools(),
            )
            tool_calls: list = [
                item
                for item in response.output
                if item.type == "function_call"
            ]

            for item in response.output:
                state.add(item.model_dump(mode="json"))

            if not tool_calls:
                print("本轮循环调用工具数为0")
                state.status = AgentStatus.COMPLETED
                return response

            for tool_call in tool_calls:
                result: ToolExecutionResult = self.executor.execute(
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments
                )

                state.add(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": (
                            str(result.output)
                            if result.success
                            else f"Tool Error: {result.error}"
                        )
                    }
                )




