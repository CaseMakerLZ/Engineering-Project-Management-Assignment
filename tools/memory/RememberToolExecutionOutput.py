"""remember 成功返回的数据结构。"""

from datetime import datetime

from pydantic import BaseModel


class RememberOutput(BaseModel):
    operation: str
    memory_id: str
    memory_type: str
    content: str
    status: str
    source_run_id: str
    superseded_memory_id: str | None
    created_at: datetime
    updated_at: datetime
