from typing import Literal

from pydantic import BaseModel, Field

from ..runs.models import RunMessage, RunStatus


# Python 服务检查自身状态后返回的数据。
class HealthResponse(BaseModel):
    status: str
    service: str


# Java 请求 Python 执行 Agent 时发送的数据。
class CreateRunRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=128)
    conversation_id: str | None = Field(default=None, max_length=128)
    prompt: str = Field(min_length=1, max_length=20_000)
    # 兼容旧版 Java/Python 请求格式；正式运行时历史由 Python 自行查询。
    context: list["ConversationContextMessage"] = Field(default_factory=list, max_length=20)


class ConversationContextMessage(BaseModel):
    # 历史消息来自用户还是 Agent。
    role: Literal["user", "assistant"]
    # 历史消息的文字内容。
    content: str = Field(min_length=1, max_length=20_000)


# 创建或取消运行后，只返回运行 ID 和当前状态。
class RunStatusResponse(BaseModel):
    run_id: str
    status: RunStatus
# 查询一次运行的过程消息时返回的数据。
class RunMessagesResponse(BaseModel):
    run_id: str
    messages: list[RunMessage]
