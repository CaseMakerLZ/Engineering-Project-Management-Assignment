from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


# Agent 任务生命周期。API、数据库和 Java 后端都使用这些稳定值沟通状态。
class RunStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# 一次 Agent 任务在服务层的内部表示，不直接等同于 HTTP 响应模型。
@dataclass(slots=True)
class RunRecord:
    run_id: str
    project_id: str | None
    prompt: str
    status: RunStatus
    result: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


# 一条已经持久化的 Agent 消息，sequence 用来保证同一任务内的顺序。
@dataclass(slots=True)
class MessageRecord:
    sequence: int
    message_type: str
    content: dict[str, Any] | str | None
    created_at: datetime
