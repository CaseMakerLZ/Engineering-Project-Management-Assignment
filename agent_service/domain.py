from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class RunStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


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


@dataclass(slots=True)
class MessageRecord:
    sequence: int
    message_type: str
    content: dict[str, Any] | str | None
    created_at: datetime
