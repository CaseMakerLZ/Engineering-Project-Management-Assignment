"""数据库读取返回的长期记忆记录，不包含数据库连接和查询逻辑。"""

from datetime import datetime

from pydantic import BaseModel


class MemoryRecord(BaseModel):
    """agent_memory 中的一条项目长期记忆，不是运行过程消息。

    同项目的不同对话共用这些记忆；source_run_id 仅供服务端追溯最后写入来源。
    """

    memory_id: str
    project_id: str
    content: str
    source_run_id: str
    updated_at: datetime
