"""SQLite 仓储的兼容导入入口。

SQLiteRunRepository 的正式实现已经与 MySQLRunRepository 放在
``agent_service.repository`` 中，便于从同一个文件阅读两种后端。
这里保留旧模块路径，避免已有测试、启动代码或外部代码立刻失效。
后续新代码应优先从 ``agent_service.repository`` 导入。
"""

from .repository import SQLiteRunRepository

__all__ = ["SQLiteRunRepository"]
