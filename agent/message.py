from dataclasses import dataclass
from enum import Enum
from typing import Any

class MessageType(str,Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"

@dataclass
class AgentMessage:
    type: MessageType
    content: Any
