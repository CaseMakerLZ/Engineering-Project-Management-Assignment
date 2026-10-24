from typing import Any

from agent.message import AgentMessage,MessageType
#所谓mapper就是映射
def response_output_to_messages(output: list[Any]) ->list[AgentMessage]:
    messages: list[AgentMessage] = []

    for item in output:
        item_content = item.model_dump(mode="json")
        if item.type == "message":
            messages.append(
                AgentMessage(
                    type=MessageType.ASSISTANT,
                    content=item_content
                )
            )
        elif item.type == "function_call":
            messages.append(
                AgentMessage(
                    type=MessageType.TOOL_CALL,
                    content=item_content
                )
            )
        #到这截止，暂不考虑其他type情况

    return messages

def messages_to_provider_input(messages: list[AgentMessage]) -> list[Any]:
    '''
    MessageType.SYSTEM
        ↓
    Responses API developer message
    ===============================
    MessageType.PROJECT_INSTRUCTIONS
        ↓
    Responses API developer message
    ===============================
    MessageType.USER
        ↓
    Responses API user message
    ===============================
    MessageType.ASSISTANT
        ↓
    Responses API assistant message
    '''
    result: list[Any] = []
    for message in messages:
        if message.type == MessageType.SYSTEM:
            # Responses API 使用 developer 消息承载高优先级规则；这里保留
            # SYSTEM 这个内部类型，避免未来系统提示词接入时发送不兼容的
            # `type=message, role=system` 输入项。
            result.append(
                {
                    "type": "message",
                    "role": "developer",
                    "content": message.content,
                }
            )
        elif message.type == MessageType.PROJECT_INSTRUCTIONS:
            # 项目级规则使用 developer 角色，和用户当前 prompt 分开。
            result.append(
                {
                    "type": "message",
                    "role": "developer",
                    "content": message.content,
                }
            )
        elif message.type == MessageType.USER:
            result.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": message.content
                }
            )
        elif message.type == MessageType.ASSISTANT:
            if isinstance(message.content, str):
                result.append({"role": "assistant", "content": message.content})
            else:
                result.append(message.content)
        elif message.type == MessageType.TOOL_CALL:
            result.append(message.content)
        elif message.type == MessageType.TOOL_RESULT:
            result.append(
                {
                    "type": "function_call_output",
                    "call_id": message.content["call_id"],
                    "output": message.content["output"]
                }
            )


    return result
