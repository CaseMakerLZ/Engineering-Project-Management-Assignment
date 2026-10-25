"""search_memory 成功返回的数据结构。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

#过程信息
class MemoryProcessMessage(BaseModel):
    sequence: int
    message_type: str
    content: dict[str, Any] | str | None
    created_at: datetime

#只被search_memory使用
class MemoryRunResult(BaseModel):
    run_id: str
    created_at: datetime
    status: str
    prompt: str
    result: str | None
    process: list[MemoryProcessMessage] | None = None


class SearchMemoryOutput(BaseModel):
    results: list[MemoryRunResult]
    returned_count: int
    has_more: bool
    truncated: bool
