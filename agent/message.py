from dataclasses import dataclass
from enum import Enum
from typing import Any

class MessageType(str,Enum):
    # SYSTEM 预留给全局系统提示词；PROJECT_INSTRUCTIONS 表示项目根目录的 AGENTS.md。
    SYSTEM = "system"
    PROJECT_INSTRUCTIONS = "project_instructions"
    USER = "user"
    ASSISTANT = "assistant"
    # 模型返回的 reasoning 项保留原始结构，供本轮后续模型调用原样回传。
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"

@dataclass
class AgentMessage:
    type: MessageType
    content: Any
