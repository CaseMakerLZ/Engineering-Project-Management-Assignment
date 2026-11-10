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
    CONTEXT_SUMMARY = "context_summary"  # 收尾保存交接说明，不作为模型原始输出伪造。
    WORKSPACE_SYNC = "workspace_sync"  # 隔离产物写回清单，单独保存，不冒充模型回答。

@dataclass
class AgentMessage:
    type: MessageType
    content: Any
    # 仅控制工作上下文，不改变落库结构；项目长期记忆不由运行时摘要改写。
    context_fixed: bool = False
