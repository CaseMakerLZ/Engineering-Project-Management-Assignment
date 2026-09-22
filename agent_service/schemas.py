from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .domain import RunStatus


class HealthResponse(BaseModel):
    status: str
    service: str


class CreateRunRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=128)
    prompt: str = Field(min_length=1, max_length=20_000)


class CreateRunResponse(BaseModel):
    run_id: str
    status: RunStatus


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    project_id: str | None
    prompt: str
    status: RunStatus
    result: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class MessageResponse(BaseModel):
    sequence: int
    message_type: str
    content: dict[str, Any] | str | None
    created_at: datetime


class RunMessagesResponse(BaseModel):
    run_id: str
    messages: list[MessageResponse]


class ErrorResponse(BaseModel):
    code: str
    message: str


class CancelRunResponse(BaseModel):
    run_id: str
    status: RunStatus

