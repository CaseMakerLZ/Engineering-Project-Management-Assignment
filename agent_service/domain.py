from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# 一次 Agent 运行从创建到结束会经历的状态。Java 和 Python 使用相同的文字。
class RunStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# 一次 Agent 运行的全部任务信息。它也直接用于查询接口的返回结果。
class Run(BaseModel):
    run_id: str
    project_id: str | None
    conversation_id: str | None
    prompt: str
    context: list[dict[str, Any]] = Field(default_factory=list)
    status: RunStatus
    result: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


# 一次运行中的一条过程消息，例如模型回答、工具调用或工具结果。
class RunMessage(BaseModel):
    sequence: int
    message_type: str
    content: dict[str, Any] | str | None
    created_at: datetime


class MemoryRecord(BaseModel):
    """一条可长期保存的结构化记忆；它不是一次运行的过程消息。它对应了agent_memory表"""

    memory_id: str
    project_id: str
    conversation_id: str
    memory_type: str
    content: str
    source_run_id: str
    supersedes_memory_id: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
