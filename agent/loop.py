from llm.client import LLMClient
from typing import Any
from tools.executor import ToolExecutor
from state import AgentState

class AgentLoop:
    def __init__(self,
                 llm: LLMClient,
                 executor: ToolExecutor) -> None:
        self.client : LLMClient = llm
        self.executor : ToolExecutor = executor

    async def run(self,state: AgentState) -> Any:
        count: int = 0
        while True:
            print(f"第{count + 1}次循环")
            response = await self.client.generate(state.get_history())

            # state.add(response.output)
            # tool_calls = [item
            #               for item in response.output
            #               if item.type == "function_call"
            #             ]
            # 上面注释的地方我感觉没有我下面几行写得好
            tool_calls: list = []
            for item in response.output:
                state.add(item.model_dump())
                if item.type == "function_call":
                    tool_calls.append(item)

            if not tool_calls:
                print("本轮循环调用工具数为0")
                return response

            for tool_call in tool_calls:
                result: Any = self.executor.execute(
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments
                )

                state.add(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": str(result)
                    }
                )

            count += 1



