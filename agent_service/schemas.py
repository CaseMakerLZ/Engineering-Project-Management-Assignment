from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .domain import RunStatus


# 健康检查接口返回的数据结构。
class HealthResponse(BaseModel):
    status: str
    service: str


# Java 创建 Agent 任务时提交的 JSON 请求体。
class CreateRunRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=128)
    prompt: str = Field(min_length=1, max_length=20_000)


# 创建任务后立即返回的异步任务凭据。
class CreateRunResponse(BaseModel):
    run_id: str
    status: RunStatus

'''
Run:        这次任务执行得怎么样？
Message:    这次任务具体经历了什么？
Memory:	    未来任务应该记住什么？
'''

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


# 对外暴露的一条消息；content 保留为 JSON 兼容结构，避免暴露 SDK 对象。
class MessageResponse(BaseModel):
    sequence: int
    message_type: str
    content: dict[str, Any] | str | None
    created_at: datetime


# 查询任务消息时的顶层响应结构。
class RunMessagesResponse(BaseModel):
    run_id: str
    messages: list[MessageResponse]


# 预留给统一错误响应的结构，后续异常体系接入时使用。
class ErrorResponse(BaseModel):
    code: str
    message: str


# 取消任务接口的响应结构。
class CancelRunResponse(BaseModel):
    run_id: str
    status: RunStatus
