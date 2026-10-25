"""remember 成功返回的数据结构。"""

from pydantic import BaseModel


class RememberOutput(BaseModel):
    memory_id: str
    content: str
