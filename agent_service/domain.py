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
    context: list[dict[str, str]] = Field(default_factory=list)
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
