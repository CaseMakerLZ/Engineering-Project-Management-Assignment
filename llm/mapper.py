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
        elif item.type == "reasoning":
            # 不能只保留可读文字：模型续接工具调用时还需要原始 reasoning 项。
            messages.append(
                AgentMessage(type=MessageType.REASONING, content=item_content)
            )
        elif item.type == "function_call":
            messages.append(
                AgentMessage(
                    type=MessageType.TOOL_CALL,
                    content=item_content
                )
            )
        # 其他未识别的输出类型仍待单独设计，不在这里冒充普通消息。

    return messages


def reasoning_display_content(item: dict[str, Any]) -> tuple[str | None, str | None]:
    """提取服务商明确返回的可读文本；不尝试解密或伪造内部推理。

    OpenAI 风格的 summary 优先作为“思考摘要”；部分兼容服务会直接返回
    content[].reasoning_text，单独标记为“可见推理文本”。两者语义不同。
    """
    for field, part_type, display_type in (
        ("summary", "summary_text", "summary"),
        ("content", "reasoning_text", "reasoning_text"),
    ):
        parts = item.get(field) or []
        if not isinstance(parts, list):
            continue
        texts = [
            part["text"]
            for part in parts
            if isinstance(part, dict)
            and part.get("type") == part_type
            and isinstance(part.get("text"), str)
            and part["text"].strip()
        ]
        if texts:
            return "\n\n".join(texts), display_type
    return None, None

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
    ===============================
    MessageType.REASONING
        ↓
    Responses API 原始 reasoning item
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
        elif message.type == MessageType.REASONING:
            # 原样回传 provider item，保留 id、summary、content 和加密状态。
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
