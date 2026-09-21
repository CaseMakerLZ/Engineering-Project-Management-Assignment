from typing import Any

from agent.message import AgentMessage,MessageType

def response_output_to_messages(output: list[Any]) ->list[AgentMessage]:
    messages: list[AgentMessage] = []

    for item in output:
        if item.type == "message":
            messages.append(
                AgentMessage(
                    type=MessageType.ASSISTANT,
                    content=item
                )
            )
        elif item.type == "function_call":
            messages.append(
                AgentMessage(
                    type=MessageType.TOOL_CALL,
                    content=item
                )
            )
        #到这截止，暂不考虑其他type情况

    return messages

def messages_to_provider_input(messages: list[AgentMessage]) -> list[Any]:
    result: list[Any] = []
    for message in messages:
        if message.type == MessageType.USER:
            result.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": message.content
                }
            )
        elif message.type == MessageType.ASSISTANT:
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