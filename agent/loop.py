from .state import AgentStatus
from llm.client import LLMClient
from typing import Any, Callable
from tools.executor import ToolExecutor, ToolExecutionResult
from tools.registry import ToolRegistry
from .message import AgentMessage, MessageType
from .state import AgentState
from llm.mapper import messages_to_provider_input, response_output_to_messages


class AgentLoop:
    def __init__(self,
                 llm: LLMClient,
                 registry: ToolRegistry,
                 executor: ToolExecutor) -> None:
        self.client : LLMClient = llm
        self.executor : ToolExecutor = executor
        self.registry: ToolRegistry = registry

    async def run(
        self, state: AgentState, *,
        on_text: Callable[[str, str], None] | None = None,
    ) -> Any:
        """on_text 是收到新文字时要调用的函数；不传时保持原来的完整回答方式。"""
        state.status = AgentStatus.RUNNING
        while True:

            if not state.can_continue():
                state.status = AgentStatus.MAX_STEPS_EXCEEDED
                return None

            state.increment_step()
            print(f"第{state.step}次循环")

            if on_text is None:
                response = await self.client.generate(
                    input=messages_to_provider_input(state.get_history()),
                    tools=self.registry.get_llm_tools(),
                )
            else:
                def receive_text(message_id: str, text: str) -> None:
                    # 不同循环的文字分开保存，即使服务商重复使用了消息 ID 也不会混在一起。
                    on_text(f"step-{state.step}:{message_id}", text)

                response = await self.client.generate(
                    input=messages_to_provider_input(state.get_history()),
                    tools=self.registry.get_llm_tools(),
                    on_text=receive_text,
                )

            messages = response_output_to_messages(response.output)

            tool_calls: list = [
                message
                for message in messages
                if message.type == MessageType.TOOL_CALL
            ]

            for message in messages:
                state.add(message)

            if not tool_calls:
                print("本轮循环调用工具数为0")
                state.status = AgentStatus.COMPLETED
                return response

            for tool_call in tool_calls:
                tool_call_content = tool_call.content
                result: ToolExecutionResult = await self.executor.execute_async(
                    tool_name=tool_call_content["name"],
                    arguments=tool_call_content["arguments"]
                )
                #TODO: 这个last_tool_result暂时没有什么作用，到时候可能可以丢掉而选择更好的方案
                state.last_tool_result = result

                message = AgentMessage(
                    type=MessageType.TOOL_RESULT,
                    content={
                        "call_id": tool_call_content["call_id"],
                        "output": (
                            str(result.output)
                            if result.success
                            else f"Tool Error [{result.error_code or 'TOOL_ERROR'}]: {result.error}"
                        )
                    }
                )

                #这里进行了一次重构
                state.add(message)
                # state.add(
                #     {
                #         "type": "function_call_output",
                #         "call_id": tool_call.call_id,
                #         "output": (
                #             str(result.output)
                #             if result.success
                #             else f"Tool Error: {result.error}"
                #         )
                #     }
                # )




