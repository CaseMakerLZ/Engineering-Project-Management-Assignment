"""把 Agent 运行数据保存到 SQLite 或 MySQL。

阅读顺序：先看 RunRepository 的方法清单，再看 MySQLRunRepository 的实现；
文件末尾的 create_run_repository 决定使用 MySQL 还是 SQLite。

本文件只负责数据库读写，不执行 Agent，也不决定模型应该记住什么：
    agent_run         一次运行的问题、结果、状态和初始上下文快照。
    agent_run_message 一次运行的过程消息，按运行内序号排列。
    agent_memory      remember 明确保存的项目长期记忆，启动时由 ContextBuilder 读取。

调用关系：
    RunService          -> create_run / get_run / update_run / append_messages
    CurrentAgentRuntime -> update_context
    ContextBuilder      -> list_recent_completed_runs / list_project_memories
    search_memory 工具  -> list_memory_runs / list_messages
    remember 工具       -> upsert_memory

单下划线开头的名称是“仅供内部使用”的 Python 约定，不是强制访问限制。
开头三个小函数只做 JSON、时间格式转换；业务层不需要直接调用它们。

RunRepository       # 运行服务需要什么
MemoryRepository    # 记忆工具需要什么

MySQLRunRepository  # 云端数据库适配器，同时满足上面两个接口
SQLiteRunRepository # 本地数据库适配器，同时满足上面两个接口
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Protocol

from .config import Settings
from .domain import MemoryRecord, Run, RunMessage, RunStatus


# 内部格式转换：数据库里的 JSON/时间 -> Python 对象，或反向转换。
def _decode_json(value: Any) -> Any:
    """把 MySQL JSON 列转为 Python 对象，供运行和过程消息的读取方法使用。

    驱动已返回 dict/list 等对象时直接使用；返回 JSON 文本时才解析。
    SQL NULL 保持为 None；非法 JSON 会抛出解析异常，不用空内容掩盖错误。
    """
    if value is None or isinstance(value, (dict, list, int, float, bool)):
        return value
    return json.loads(value)


def _db_datetime(value: datetime | None) -> datetime | None:
    """写库前把时间转为 UTC，再去掉时区标记以适配 MySQL DATETIME。

    例如 08:00+08:00 写为 00:00；DATETIME 列本身不保存时区信息。
    调用方应提供带时区的时间；None 表示尚未开始/结束，仍写为 SQL NULL。
    """
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_datetime(value: datetime | None) -> datetime | None:
    """读库后给没有时区的 DATETIME 补上 UTC，供 Run/RunMessage 使用。

    这是与 _db_datetime 配套的读取约定，不是把本地时间猜成 UTC。
    已带时区的值原样保留，None 仍表示没有时间。
    """
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class RunRepository(Protocol):
    """RunService 需要的数据保存功能。(接口)

    也供 Runtime 和 ContextBuilder 使用。这里只声明方法，不写 SQL；记忆工具
    依赖下方独立的 MemoryRepository，不把所有数据库能力混在同一个接口里。
    Protocol 表达“具备这些方法即可”，SQLite/MySQL 不必显式继承它。
    两个实现返回相同的 Run、RunMessage，上层不处理 SQL 差异。
    """

    # 连接准备与本轮运行：由应用启动、RunService 和 Runtime 使用。
    def initialize(self) -> None:
        """确保 Python 所需表结构存在；可重复调用，不清空已有数据。"""
        ...

    def create_run(self, run: Run) -> Run:
        """把新 Run 写入 agent_run，返回传入的 Run；不执行任务。"""
        ...

    def get_run(self, run_id: str) -> Run | None:
        """按 ID 读取完整 Run；不存在时返回 None，不附带过程消息。"""
        ...

    def update_run(self, run: Run) -> Run:
        """按 ID 更新状态、结果、错误和开始/结束时间，不更新上下文。"""
        ...

    def update_context(self, run_id: str, context: list[dict[str, Any]]) -> None:
        """覆盖 agent_run.context_json，保存 Runtime 实际使用的初始上下文。"""
        ...

    # 过程消息：与 agent_run 的最终 result 分开保存。
    def append_messages(self, run_id: str, messages: list[tuple[str, Any]]) -> None:
        """追加 (消息类型, 消息内容) 列表，自动续接运行内序号；空列表不写入。"""
        ...

    def list_messages(self, run_id: str) -> list[RunMessage]:
        """按序号返回该 Run 全部过程消息；无消息返回 []，本方法不裁剪或脱敏。"""
        ...

    # 历史读取：ContextBuilder 使用近期历史；记忆工具使用独立的 MemoryRepository。
    def list_recent_completed_runs(
        self, project_id: str, conversation_id: str, before_created_at: datetime, limit: int
    ) -> list[Run]:
        """供 ContextBuilder 取本轮之前同项目同对话的最近已完成运行，正序返回。"""
        ...


class MemoryRepository(Protocol):
    """记忆工具依赖的最小仓储接口，也声明项目长期记忆读取能力。

    这不是一个单独的数据库对象。实际传入的对象仍然是
    ``SQLiteRunRepository`` 或 ``MySQLRunRepository``，这里只声明
    ``search_memory``、``remember`` 和长期记忆读取所需的方法，避免把记忆能力混入
    RunService 使用的 ``RunRepository`` 接口。
    """

    def list_memory_runs(
        self,
        project_id: str,
        conversation_id: str,
        before_created_at: datetime,
        start_created_at: datetime,
        end_created_at: datetime,
        limit: int,
    ) -> list[Run]:
        """查询同项目、同对话、时间范围内的已完成运行，供 search_memory 使用。"""
        ...

    def list_messages(self, run_id: str) -> list[RunMessage]:
        """读取某次运行的过程消息，供 search_memory 的过程回溯使用。"""
        ...

    def upsert_memory(
        self,
        *,
        memory_id: str,
        project_id: str,
        content: str,
        source_run_id: str,
        now: datetime,
        create: bool,
    ) -> MemoryRecord:
        """remember 写入入口；create=True 仅新增，False 仅更新已有的同项目记录。"""
        ...

    def list_project_memories(self, project_id: str) -> list[MemoryRecord]:
        """返回项目全部长期记忆，按更新时间、ID 正序；不按对话过滤或静默裁剪。"""
        ...


class MySQLRunRepository:
    """Python 服务使用的 MySQL 数据保存实现。(上面接口的实现)

    每次读写各开一个连接，并在 finally 中关闭；当前没有连接池。
    公共方法先调用 initialize，保证建表完成后再读写。
    """

    # 建表顺序：先建运行表，再建引用它的过程表、长期记忆表。
    # IF NOT EXISTS 不会重建已有表，也不等于通用的表结构迁移机制。
    _schema = (
        """
        CREATE TABLE IF NOT EXISTS agent_run (
            run_id VARCHAR(36) PRIMARY KEY,
            project_id VARCHAR(128), conversation_id VARCHAR(128),
            prompt TEXT NOT NULL, context_json JSON NOT NULL,
            status VARCHAR(16) NOT NULL, result MEDIUMTEXT, error TEXT,
            created_at DATETIME(6) NOT NULL, started_at DATETIME(6),
            finished_at DATETIME(6)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_run_message (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            run_id VARCHAR(36) NOT NULL, sequence_no INT NOT NULL,
            message_type VARCHAR(32) NOT NULL, content_json JSON,
            created_at DATETIME(6) NOT NULL,
            UNIQUE KEY uk_agent_run_message_sequence (run_id, sequence_no),
            CONSTRAINT fk_agent_run_message_run FOREIGN KEY (run_id)
                REFERENCES agent_run(run_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_memory (
            memory_id VARCHAR(64) PRIMARY KEY,
            project_id VARCHAR(128) NOT NULL,
            content TEXT NOT NULL,
            source_run_id VARCHAR(36) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            KEY idx_agent_memory_project_updated (project_id, updated_at, memory_id),
            CONSTRAINT fk_agent_memory_source_run FOREIGN KEY (source_run_id)
                REFERENCES agent_run(run_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    )

    def __init__(self, settings: Settings) -> None:
        """保存数据库配置和初始化锁；构造对象时还不连接 MySQL。"""
        self.settings = settings
        self._initialize_lock = Lock()
        self._initialized = False

    def _connect(self):
        """内部方法：按 Settings 新建一个 MySQL 连接，由调用方法负责关闭。

        放在这里统一处理连接参数；只在真正使用 MySQL 时导入驱动。
        这与 SQLite 复用单个连接不同，不要把它当作连接池。
        """
        try:
            import mysql.connector
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "MySQL repository requires mysql-connector-python; install requirements.txt"
            ) from exc
        return mysql.connector.connect(
            host=self.settings.mysql_host, port=self.settings.mysql_port,
            user=self.settings.mysql_user, password=self.settings.mysql_password,
            database=self.settings.mysql_database,
        )

    def initialize(self) -> None:
        """首次使用时创建三张 Python 数据表，成功后本实例不重复执行建表。

        锁只避免同一实例的多个线程同时初始化，不是跨进程数据库锁。
        不清空数据，不初始化 Java 的业务表，也不自动升级已有 MySQL 列。
        """
        if self._initialized:
            return
        with self._initialize_lock:
            if self._initialized:
                return
            connection = self._connect()
            try:
                cursor = connection.cursor()
                for statement in self._schema:
                    cursor.execute(statement)
                connection.commit()
                self._initialized = True
            finally:
                connection.close()

    def create_run(self, run: Run) -> Run:
        """由 RunService 创建 agent_run 记录，成功写库后返回同一个 Run。

        UUID、CREATED 状态和创建时间由调用方生成；仓储只保存，不启动 Agent。
        context 被编码为 JSON；正式链路创建时为空，运行前由 update_context 更新。
        """
        self.initialize()
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO agent_run
                (run_id, project_id, conversation_id, prompt, context_json, status,
                 result, error, created_at, started_at, finished_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (run.run_id, run.project_id, run.conversation_id, run.prompt,
                 json.dumps(run.context, ensure_ascii=False), run.status.value,
                 run.result, run.error, _db_datetime(run.created_at),
                 _db_datetime(run.started_at), _db_datetime(run.finished_at)),
            )
            connection.commit()
            return run
        finally:
            connection.close()

    def get_run(self, run_id: str) -> Run | None:
        """供任务查询/执行/取消按 run_id 读取 agent_run，不存在返回 None。

        包含反序列化后的 context，但不联查过程消息或长期记忆。
        此方法只按 ID 查询；调用入口的访问权限不由本方法判断。
        """
        self.initialize()
        connection = self._connect()
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM agent_run WHERE run_id = %s", (run_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return Run(
                run_id=row["run_id"], project_id=row["project_id"],
                conversation_id=row["conversation_id"], prompt=row["prompt"],
                context=_decode_json(row["context_json"]),
                status=RunStatus(row["status"]), result=row["result"],
                error=row["error"], created_at=_utc_datetime(row["created_at"]),
                started_at=_utc_datetime(row["started_at"]),
                finished_at=_utc_datetime(row["finished_at"]),
            )
        finally:
            connection.close()

    def list_recent_completed_runs(
        self, project_id: str, conversation_id: str, before_created_at: datetime, limit: int
    ) -> list[Run]:
        """读取当前运行之前、同项目同对话的最近已完成轮次，按时间正序返回。(agent_run)

        调用方是 ContextBuilder，用 prompt/result 组装新一轮近期历史。
        before_created_at 是当前 Run 创建时间（不含），limit 必须大于 0。
        SQL 先倒序取最近 limit 条，再反转为从旧到新，便于按聊天顺序注入。
        无符合记录返回 []；此查询也读取 context_json，但不加载过程消息。
        """
        if limit <= 0:
            raise ValueError("历史轮次数量限制必须大于 0")
        self.initialize()
        connection = self._connect()
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT run_id, project_id, conversation_id, prompt, context_json,
                       status, result, error, created_at, started_at, finished_at
                FROM agent_run
                WHERE project_id = %s AND conversation_id = %s
                  AND status = %s AND created_at < %s
                ORDER BY created_at DESC, run_id DESC
                LIMIT %s
                """,
                (project_id, conversation_id, RunStatus.COMPLETED.value,
                 _db_datetime(before_created_at), limit),
            )
            rows = cursor.fetchall()
            return [
                Run(
                    run_id=row["run_id"], project_id=row["project_id"],
                    conversation_id=row["conversation_id"], prompt=row["prompt"],
                    context=_decode_json(row["context_json"]),
                    status=RunStatus(row["status"]), result=row["result"],
                    error=row["error"], created_at=_utc_datetime(row["created_at"]),
                    started_at=_utc_datetime(row["started_at"]),
                    finished_at=_utc_datetime(row["finished_at"]),
                )
                for row in reversed(rows)
            ]
        finally:
            connection.close()

    def list_memory_runs(
        self,
        project_id: str,
        conversation_id: str,
        before_created_at: datetime,
        start_created_at: datetime,
        end_created_at: datetime,
        limit: int,
    ) -> list[Run]:
        """读取记忆工具的候选运行；文本筛选由工具服务在边界内完成。

        由 search_memory 调用，只查 agent_run，不查 agent_memory。
        范围为同项目、同对话、COMPLETED，且创建时间在 [start, end) 内，
        同时早于 before_created_at（当前 Run 的创建时间）。时间窗口由工具层计算。
        limit 是候选数量上限，不一定等于工具最终返回数量，必须大于 0。
        先取最近的候选，再按从旧到新返回；没有结果返回 []。
        为减少读取量不取 context_json/过程消息，返回的 Run.context 固定为空。
        """
        if limit <= 0:
            raise ValueError("记忆检索数量限制必须大于 0")
        self.initialize()
        connection = self._connect()
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT run_id, project_id, conversation_id, prompt,
                       status, result, error, created_at, started_at, finished_at
                FROM agent_run
                WHERE project_id = %s AND conversation_id = %s
                  AND status = %s
                  AND created_at >= %s AND created_at < %s
                  AND created_at < %s
                ORDER BY created_at DESC, run_id DESC
                LIMIT %s
                """,
                (
                    project_id,
                    conversation_id,
                    RunStatus.COMPLETED.value,
                    _db_datetime(start_created_at),
                    _db_datetime(end_created_at),
                    _db_datetime(before_created_at),
                    limit,
                ),
            )
            rows = cursor.fetchall()
            return [
                Run(
                    run_id=row["run_id"], project_id=row["project_id"],
                    conversation_id=row["conversation_id"], prompt=row["prompt"],
                    context=[],
                    status=RunStatus(row["status"]), result=row["result"],
                    error=row["error"], created_at=_utc_datetime(row["created_at"]),
                    started_at=_utc_datetime(row["started_at"]),
                    finished_at=_utc_datetime(row["finished_at"]),
                )
                for row in reversed(rows)
            ]
        finally:
            connection.close()

    def list_project_memories(self, project_id: str) -> list[MemoryRecord]:
        """读取同项目全部长期记忆；项目索引负责缩小范围，不混入其他项目内容。"""
        self.initialize()
        connection = self._connect()
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT memory_id, project_id, content, source_run_id, updated_at "
                "FROM agent_memory WHERE project_id = %s ORDER BY updated_at, memory_id",
                (project_id,),
            )
            return [
                MemoryRecord(
                    memory_id=row["memory_id"], project_id=row["project_id"],
                    content=row["content"], source_run_id=row["source_run_id"],
                    updated_at=_utc_datetime(row["updated_at"]),
                )
                for row in cursor.fetchall()
            ]
        finally:
            connection.close()

    def upsert_memory(
        self,
        *,
        memory_id: str,
        project_id: str,
        content: str,
        source_run_id: str,
        now: datetime,
        create: bool,
    ) -> MemoryRecord:
        """在短事务内新增或原地更新项目记忆，不保存状态和历史版本。

        create 由服务端根据模型是否传 ID 决定；新增 ID 冲突时失败，
        更新未知/其他项目 ID 时失败，不能把错误 ID 当成新记忆。
        来源 Run 必须存在且属于当前项目；跨对话更新同项目记忆是允许的。
        行锁防止写入交错；同时更新同一条时，以最后提交的完整内容为准。
        当前不做乐观版本校验、自动合并或死锁自动重试。
        """
        self.initialize()
        connection = self._connect()
        try:
            connection.start_transaction()
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT project_id FROM agent_run WHERE run_id = %s FOR UPDATE",
                (source_run_id,),
            )
            source_run = cursor.fetchone()
            if source_run is None:
                raise ValueError("source_run_id 对应的运行不存在")
            if source_run["project_id"] != project_id:
                raise ValueError("source_run_id 不属于当前项目")

            if create:
                # 不使用 ON DUPLICATE KEY UPDATE，避免极小概率 ID 冲突覆盖旧记忆。
                cursor.execute(
                    "INSERT INTO agent_memory "
                    "(memory_id, project_id, content, source_run_id, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (memory_id, project_id, content, source_run_id, _db_datetime(now)),
                )
            else:
                cursor.execute(
                    "SELECT memory_id FROM agent_memory "
                    "WHERE memory_id = %s AND project_id = %s FOR UPDATE",
                    (memory_id, project_id),
                )
                if cursor.fetchone() is None:
                    raise ValueError("memory_id 不存在或不属于当前项目")
                cursor.execute(
                    "UPDATE agent_memory SET content = %s, source_run_id = %s, updated_at = %s "
                    "WHERE memory_id = %s AND project_id = %s",
                    (content, source_run_id, _db_datetime(now), memory_id, project_id),
                )
            record = MemoryRecord(
                memory_id=memory_id, project_id=project_id, content=content,
                source_run_id=source_run_id, updated_at=now,
            )
            connection.commit()
            return record
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def update_run(self, run: Run) -> Run:
        """把 RunService 已决定的运行状态、结果、错误和起止时间写回 agent_run。

        按 run_id 更新，不改 prompt/项目/对话/context，也不自行判断状态流转是否合法。
        返回传入的 Run；当前不根据影响行数判断 ID 是否存在，调用方应先查询。
        """
        self.initialize()
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE agent_run SET status = %s, result = %s, error = %s,
                    started_at = %s, finished_at = %s WHERE run_id = %s
                """,
                (run.status.value, run.result, run.error,
                 _db_datetime(run.started_at), _db_datetime(run.finished_at),
                 run.run_id),
            )
            connection.commit()
            return run
        finally:
            connection.close()

    def update_context(self, run_id: str, context: list[dict[str, Any]]) -> None:
        """保存本次运行真正注入 Agent 的初始上下文快照。

        由 CurrentAgentRuntime 在启动 Agent 前调用，覆盖 agent_run.context_json。
        context 是已组装好的消息列表，不包含随后追加的当前 prompt；本方法只存储，
        不查询历史、不组装上下文，也不修改该 Run 的状态或最终结果。无返回值。
        """
        self.initialize()
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE agent_run SET context_json = %s WHERE run_id = %s",
                (json.dumps(context, ensure_ascii=False), run_id),
            )
            connection.commit()
        finally:
            connection.close()

    def append_messages(self, run_id: str, messages: list[tuple[str, Any]]) -> None:
        """由 RunService 将本次运行的过程消息追加到 agent_run_message。

        messages 每项为 (message_type, content)，content 必须能编码为 JSON。
        先读取该 Run 的最大序号，再从下一号连续追加；空列表直接返回。
        本批消息使用同一个保存时间，表示入库时间而非各事件真实发生时间。
        当前服务成功运行返回后才调用，不是运行中逐条落库；本方法不负责脱敏。
        整批在一次事务中提交；现有序号锁与唯一约束不等于多实例重试机制。
        """
        if not messages:
            return
        self.initialize()
        connection = self._connect()
        try:
            connection.start_transaction()
            cursor = connection.cursor()
            cursor.execute(
                "SELECT COALESCE(MAX(sequence_no), 0) FROM agent_run_message "
                "WHERE run_id = %s FOR UPDATE", (run_id,)
            )
            sequence = cursor.fetchone()[0]
            now = _db_datetime(datetime.now(timezone.utc))
            cursor.executemany(
                """
                INSERT INTO agent_run_message
                (run_id, sequence_no, message_type, content_json, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [(run_id, sequence + offset, message_type,
                  json.dumps(content, ensure_ascii=False), now)
                 for offset, (message_type, content) in enumerate(messages, start=1)],
            )
            connection.commit()
        finally:
            connection.close()

    def list_messages(self, run_id: str) -> list[RunMessage]:
        """供过程查询和 search_memory 读取一个 Run 的全部过程消息，按序号升序。

        从 agent_run_message 解码 JSON 后返回 RunMessage 列表，无消息返回 []。
        不分页、不限制长度、不移除敏感字段；search_memory 在工具层裁剪和脱敏。
        """
        self.initialize()
        connection = self._connect()
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT sequence_no, message_type, content_json, created_at
                FROM agent_run_message WHERE run_id = %s ORDER BY sequence_no
                """, (run_id,),
            )
            return [
                RunMessage(
                    sequence=row["sequence_no"], message_type=row["message_type"],
                    content=_decode_json(row["content_json"])
                    if row["content_json"] is not None else None,
                    created_at=_utc_datetime(row["created_at"]),
                )
                for row in cursor.fetchall()
            ]
        finally:
            connection.close()


class SQLiteRunRepository:
    """把 Agent 运行、上下文和过程消息保存到同一个 SQLite 文件。

    也保存 remember 的长期记忆。公共方法含义与 MySQL 版保持一致，
    只把连接、SQL 占位符和数据格式差异留在本文件。
    """

    # 按依赖顺序创建运行表、过程表、记忆表，最后创建记忆范围索引。
    # _schema 是内部 SQL 清单，不是模型参数，也不是新的配置入口。
    _schema = (
        """
        CREATE TABLE IF NOT EXISTS agent_run (
            run_id TEXT PRIMARY KEY,
            project_id TEXT,
            conversation_id TEXT,
            prompt TEXT NOT NULL,
            context_json TEXT NOT NULL,
            status TEXT NOT NULL,
            result TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_run_message (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            sequence_no INTEGER NOT NULL,
            message_type TEXT NOT NULL,
            content_json TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(run_id, sequence_no),
            FOREIGN KEY(run_id) REFERENCES agent_run(run_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_memory (
            memory_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            content TEXT NOT NULL,
            source_run_id TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(source_run_id) REFERENCES agent_run(run_id)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_agent_memory_project_updated
        ON agent_memory(project_id, updated_at, memory_id)
        """,
    )

    def __init__(self, database_path: str | Path, *, timeout_seconds: float = 5.0) -> None:
        """解析数据库路径并准备父目录、连接锁；此时尚未连接或建表。

        timeout_seconds 是数据库被占用时等待锁的时长，必须大于 0，
        不是 Agent 运行超时。真正连接在首次 initialize/读写时建立。
        """
        if timeout_seconds <= 0:
            raise ValueError("SQLite timeout_seconds 必须大于 0")

        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        # SQLite 连接只在当前 Python 进程内复用。
        # check_same_thread=False 允许 FastAPI 请求线程和后台任务线程访问同一连接，
        # _connection_lock 则保证同一时刻只有一个操作使用它，避免事务互相污染。
        self._connection_lock = RLock()
        self._connection: sqlite3.Connection | None = None
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        """按需创建并返回当前仓储实例复用的连接。

        调用方必须先持有 _connection_lock。连接不能跨进程共享；Java 进程
        使用自己的数据库连接，Python 进程内的请求和后台任务则复用这一条连接。

        row_factory 让查询结果能按列名读取；foreign_keys 开启外键检查；
        busy_timeout 设置等锁时间；WAL 减少读写互相阻塞，但不允许多个写者同时写。
        isolation_level=None 关闭驱动的隐式事务，写入方法用 BEGIN IMMEDIATE
        显式开启事务，并在成功/失败时提交/回滚。
        """
        if self._connection is None:
            connection = sqlite3.connect(
                self.database_path,
                timeout=self.timeout_seconds,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                f"PRAGMA busy_timeout = {int(self.timeout_seconds * 1000)}"
            )
            # WAL 允许读取与写入更好地并行；仍然需要用短事务控制写入竞争。
            connection.execute("PRAGMA journal_mode = WAL")
            self._connection = connection
        return self._connection

    def initialize(self) -> None:
        """按当前定义幂等创建数据表，不升级或搬运旧结构与旧数据。

        建表在同一写事务内完成；失败回滚，不清空现有数据库。
        """
        if self._initialized:
            return

        with self._connection_lock:
            if self._initialized:
                return
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                for statement in self._schema:
                    connection.execute(statement)
                connection.commit()
                self._initialized = True
            except Exception:
                connection.rollback()
                raise

    def close(self) -> None:
        """关闭当前仓储复用的连接；关闭后再次使用会按需重新初始化。

        用于释放连接资源，不删除数据库文件或已有数据。
        """
        with self._connection_lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            self._initialized = False

    def create_run(self, run: Run) -> Run:
        """保存一条初始运行记录及其启动上下文。

        由 RunService 创建 agent_run；UUID、状态、时间均已包含在传入 Run 中。
        正式链路初始 context 为空，Runtime 组装后再通过 update_context 覆盖。
        成功返回传入的 Run；重复 run_id 等数据库错误会回滚并向上抛出，不执行 Agent。
        """
        self.initialize()
        with self._connection_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO agent_run
                    (run_id, project_id, conversation_id, prompt, context_json, status,
                     result, error, created_at, started_at, finished_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.run_id,
                        run.project_id,
                        run.conversation_id,
                        run.prompt,
                        json.dumps(run.context, ensure_ascii=False),
                        run.status.value,
                        run.result,
                        run.error,
                        _to_sqlite_datetime(run.created_at),
                        _to_sqlite_datetime(run.started_at),
                        _to_sqlite_datetime(run.finished_at),
                    ),
                )
                connection.commit()
                return run
            except Exception:
                connection.rollback()
                raise

    def get_run(self, run_id: str) -> Run | None:
        """按运行 ID 读取一条运行记录。

        供任务查询、执行和取消使用；包含 context_json 解码后的 context，
        不附带过程消息/长期记忆。不存在返回 None；入口访问权限不由本方法判断。
        """
        self.initialize()
        with self._connection_lock:
            connection = self._connect()
            row = connection.execute(
                "SELECT * FROM agent_run WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            return _run_from_row(row) if row is not None else None

    def list_recent_completed_runs(
        self, project_id: str, conversation_id: str, before_created_at: datetime, limit: int
    ) -> list[Run]:
        """读取当前运行之前、同项目同对话的最近已完成轮次，按时间正序返回。

        由 ContextBuilder 调用，用这些 Run 的 prompt/result 组装近期聊天历史。
        before_created_at 为当前 Run 创建时间（不含），limit 必须大于 0。
        SQL 先倒序取最近 limit 条，再反转为从旧到新；没有历史返回 []。
        查询包含 context_json，但不会顺带读取过程消息或长期记忆表。
        """
        if limit <= 0:
            raise ValueError("历史轮次数量限制必须大于 0")
        self.initialize()
        with self._connection_lock:
            connection = self._connect()
            rows = connection.execute(
                """
                SELECT run_id, project_id, conversation_id, prompt, context_json,
                       status, result, error, created_at, started_at, finished_at
                FROM agent_run
                WHERE project_id = ? AND conversation_id = ?
                  AND status = ? AND created_at < ?
                ORDER BY created_at DESC, run_id DESC
                LIMIT ?
                """,
                (project_id, conversation_id, RunStatus.COMPLETED.value,
                 _to_sqlite_datetime(before_created_at), limit),
            ).fetchall()
            return [_run_from_row(row) for row in reversed(rows)]

    def list_memory_runs(
        self,
        project_id: str,
        conversation_id: str,
        before_created_at: datetime,
        start_created_at: datetime,
        end_created_at: datetime,
        limit: int,
    ) -> list[Run]:
        """读取记忆工具的候选运行；文本筛选由工具服务在边界内完成。

        由 search_memory 调用，查询 agent_run，不查询 agent_memory。
        范围为同项目、同对话、COMPLETED，且创建时间在 [start, end) 内，
        同时早于 before_created_at（当前 Run 创建时间）。时间窗口由工具层计算。
        limit 是候选数量上限，不一定等于工具最终返回数量，必须大于 0。
        先选最近的候选，再按从旧到新返回；无结果返回 []。
        不读取 context_json/过程消息，因此返回的 Run.context 固定为 []。
        """
        if limit <= 0:
            raise ValueError("记忆检索数量限制必须大于 0")
        self.initialize()
        with self._connection_lock:
            connection = self._connect()
            rows = connection.execute(
                """
                SELECT run_id, project_id, conversation_id, prompt,
                       status, result, error, created_at, started_at, finished_at
                FROM agent_run
                WHERE project_id = ? AND conversation_id = ?
                  AND status = ?
                  AND created_at >= ? AND created_at < ?
                  AND created_at < ?
                ORDER BY created_at DESC, run_id DESC
                LIMIT ?
                """,
                (
                    project_id,
                    conversation_id,
                    RunStatus.COMPLETED.value,
                    _to_sqlite_datetime(start_created_at),
                    _to_sqlite_datetime(end_created_at),
                    _to_sqlite_datetime(before_created_at),
                    limit,
                ),
            ).fetchall()
            return [_memory_run_from_row(row) for row in reversed(rows)]

    def list_project_memories(self, project_id: str) -> list[MemoryRecord]:
        """读取同项目全部长期记忆，按更新时间、ID 正序，不依赖对话 ID。"""
        self.initialize()
        with self._connection_lock:
            rows = self._connect().execute(
                "SELECT memory_id, project_id, content, source_run_id, updated_at "
                "FROM agent_memory WHERE project_id = ? ORDER BY updated_at, memory_id",
                (project_id,),
            ).fetchall()
            return [
                MemoryRecord(
                    memory_id=row["memory_id"], project_id=row["project_id"],
                    content=row["content"], source_run_id=row["source_run_id"],
                    updated_at=_from_sqlite_datetime(row["updated_at"]),
                )
                for row in rows
            ]

    def upsert_memory(
        self,
        *,
        memory_id: str,
        project_id: str,
        content: str,
        source_run_id: str,
        now: datetime,
        create: bool,
    ) -> MemoryRecord:
        """新增或原地更新项目记忆；严格区分创建与更新，不保存旧版本。

        BEGIN IMMEDIATE 保证来源校验、已有记录校验和写入一起成功或回滚。
        更新范围只限定项目，同项目不同对话可以更新；未知 ID 不转为新增。
        多个写者串行提交，同一条记忆以最后提交的完整内容为准，不自动合并。
        """
        self.initialize()
        with self._connection_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                source_run = connection.execute(
                    "SELECT project_id FROM agent_run WHERE run_id = ?",
                    (source_run_id,),
                ).fetchone()
                if source_run is None:
                    raise ValueError("source_run_id 对应的运行不存在")
                if source_run["project_id"] != project_id:
                    raise ValueError("source_run_id 不属于当前项目")

                if create:
                    # 普通 INSERT 在 ID 冲突时失败，不覆盖其他记忆。
                    connection.execute(
                        "INSERT INTO agent_memory "
                        "(memory_id, project_id, content, source_run_id, updated_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (memory_id, project_id, content, source_run_id, _to_sqlite_datetime(now)),
                    )
                else:
                    existing = connection.execute(
                        "SELECT memory_id FROM agent_memory WHERE memory_id = ? AND project_id = ?",
                        (memory_id, project_id),
                    ).fetchone()
                    if existing is None:
                        raise ValueError("memory_id 不存在或不属于当前项目")
                    connection.execute(
                        "UPDATE agent_memory SET content = ?, source_run_id = ?, updated_at = ? "
                        "WHERE memory_id = ? AND project_id = ?",
                        (content, source_run_id, _to_sqlite_datetime(now), memory_id, project_id),
                    )
                record = MemoryRecord(
                    memory_id=memory_id, project_id=project_id, content=content,
                    source_run_id=source_run_id, updated_at=now,
                )
                connection.commit()
                return record
            except Exception:
                connection.rollback()
                raise

    def update_run(self, run: Run) -> Run:
        """更新运行状态、结果和时间字段。

        RunService 决定状态变化后，按 run_id 写回 agent_run；不改 prompt、
        项目/对话归属或 context，也不自行检查状态流转规则。
        返回传入的 Run；不根据更新行数判断是否存在，调用方应先查记录。
        """
        self.initialize()
        with self._connection_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    UPDATE agent_run
                    SET status = ?, result = ?, error = ?,
                        started_at = ?, finished_at = ?
                    WHERE run_id = ?
                    """,
                    (
                        run.status.value,
                        run.result,
                        run.error,
                        _to_sqlite_datetime(run.started_at),
                        _to_sqlite_datetime(run.finished_at),
                        run.run_id,
                    ),
                )
                connection.commit()
                return run
            except Exception:
                connection.rollback()
                raise

    def update_context(self, run_id: str, context: list[dict[str, Any]]) -> None:
        """保存本次运行真正注入 Agent 的初始上下文快照。

        由 CurrentAgentRuntime 在启动 Agent 前调用，覆盖 agent_run.context_json。
        context 已由上层组装，不包含随后追加的当前 prompt；这里只做 JSON 保存，
        不查询历史、不改变运行状态/最终结果。成功无返回值，失败回滚。
        """
        self.initialize()
        with self._connection_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE agent_run SET context_json = ? WHERE run_id = ?",
                    (json.dumps(context, ensure_ascii=False), run_id),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def append_messages(self, run_id: str, messages: list[tuple[str, Any]]) -> None:
        """在一个短事务中追加消息并分配连续序号。

        由 RunService 向 agent_run_message 追加 (message_type, content) 列表；
        content 需能编码为 JSON。序号从该 Run 已有最大序号的下一号开始，空列表不写入。
        BEGIN IMMEDIATE 在读取序号前开启写事务；本批写入一起成功或回滚。
        本批使用同一个入库时间，不表示每个事件的真实发生时间。
        当前服务成功运行返回后才调用，不是运行中逐条落库；本方法不做脱敏。
        """
        if not messages:
            return

        self.initialize()
        with self._connection_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence_no), 0) FROM agent_run_message "
                    "WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0]
                now = _to_sqlite_datetime(datetime.now(timezone.utc))
                connection.executemany(
                    """
                    INSERT INTO agent_run_message
                    (run_id, sequence_no, message_type, content_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            run_id,
                            sequence + offset,
                            message_type,
                            json.dumps(content, ensure_ascii=False),
                            now,
                        )
                        for offset, (message_type, content) in enumerate(messages, start=1)
                    ],
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_messages(self, run_id: str) -> list[RunMessage]:
        """按运行内序号读取过程消息。

        供过程查询和 search_memory 使用，返回该 Run 全部 RunMessage；无记录返回 []。
        这里只解码 JSON/时间，不分页、不限制内容长度、不移除敏感字段。
        search_memory 的数量裁剪和展示内容处理在工具层执行。
        """
        self.initialize()
        with self._connection_lock:
            connection = self._connect()
            rows = connection.execute(
                """
                SELECT sequence_no, message_type, content_json, created_at
                FROM agent_run_message
                WHERE run_id = ?
                ORDER BY sequence_no
                """,
                (run_id,),
            ).fetchall()
            return [
                RunMessage(
                    sequence=row["sequence_no"],
                    message_type=row["message_type"],
                    content=_decode_sqlite_json(row["content_json"]),
                    created_at=_from_sqlite_datetime(row["created_at"]),
                )
                for row in rows
            ]


# 内部格式转换：下列函数不读写数据库，也不决定业务规则。
# 保留在本文件，是因为 SQLite 的文本时间和 Row 格式与 MySQL 不同。
def _to_sqlite_datetime(value: datetime | None) -> str | None:
    """把时间转成带 UTC 偏移的 ISO 文本，写入 SQLite 的 TEXT 时间列。

    调用方应提供带时区时间，例如 08:00+08:00 转为 00:00+00:00；None 保持为空。
    同一写入格式便于按文本比较时间，区别于 MySQL 写入不带时区的 DATETIME。
    """
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _from_sqlite_datetime(value: str | None) -> datetime | None:
    """把 SQLite 时间文本解析为 datetime，供运行/消息读取方法使用。

    兼容 Java 的 UTC 结尾 Z；文本没带时区时按 UTC 解释，已带偏移时保持该偏移。
    SQL NULL 返回 None；非法文本抛解析异常，而不是伪造一个时间。
    """
    if value is None:
        return None
    # Java OffsetDateTime.toString() 对 UTC 使用结尾 `Z`；Python 3.10 的
    # datetime.fromisoformat 只接受 `+00:00`，因此在解析前统一转换。
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _decode_sqlite_json(value: str | None) -> Any:
    """把 TEXT 列中的 JSON 还原为 Python 对象，供 context/过程消息读取使用。

    SQL NULL 返回 None；无效 JSON 抛解析异常，不静默替换成空列表。
    """
    if value is None:
        return None
    return json.loads(value)


def _run_from_row(row: sqlite3.Row) -> Run:
    """把含 context_json 的完整数据库行转为 Run，供单条查询和近期历史查询使用。

    集中处理列名、状态枚举、JSON 和时间转换，避免两个查询重复维护同一段映射。
    row 必须存在；“没查到”的情况由 get_run 在调用本函数前处理。
    """
    return Run(
        run_id=row["run_id"],
        project_id=row["project_id"],
        conversation_id=row["conversation_id"],
        prompt=row["prompt"],
        context=_decode_json(row["context_json"]),
        status=RunStatus(row["status"]),
        result=row["result"],
        error=row["error"],
        created_at=_from_sqlite_datetime(row["created_at"]),
        started_at=_from_sqlite_datetime(row["started_at"]),
        finished_at=_from_sqlite_datetime(row["finished_at"]),
    )


def _memory_run_from_row(row: sqlite3.Row) -> Run:
    """把记忆查询的精简列转换为 Run，不要求读取 context_json。

    仅由 list_memory_runs 调用；这里的“记忆查询”指回溯历史任务，不是读 agent_memory。
    查询故意省略了 context_json，因此返回 context=[]，不代表原记录没有上下文。
    与 _run_from_row 分开是为了适配不同查询列，不是额外的记忆处理流程。
    """
    return Run(
        run_id=row["run_id"],
        project_id=row["project_id"],
        conversation_id=row["conversation_id"],
        prompt=row["prompt"],
        context=[],
        status=RunStatus(row["status"]),
        result=row["result"],
        error=row["error"],
        created_at=_from_sqlite_datetime(row["created_at"]),
        started_at=_from_sqlite_datetime(row["started_at"]),
        finished_at=_from_sqlite_datetime(row["finished_at"]),
    )

# 启动选择入口：业务层不应在每次读写时自行判断数据库类型。
def create_run_repository(settings: Settings) -> RunRepository:
    """根据配置创建本地或云端的运行记录仓储。
    云端/本地运行转化工厂(SQLite/MySQL 选择层)
    选择逻辑集中在启动边界，RunService 仍然只依赖 RunRepository 接口。
    ``auto`` 是默认值：本地模式使用 SQLite，云端模式使用 MySQL。

    显式指定 sqlite/mysql 时按指定值创建；不认识的值抛 ValueError。
    返回仓储对象，不在这里读写运行记录；SQLite 构造时会准备数据库父目录，
    真正连接与建表由 initialize 或首次业务读写触发。
    """
    backend = settings.storage_backend.lower()
    if backend == "auto":
        backend = "sqlite" if settings.execution_mode.lower() == "local" else "mysql"

    if backend == "sqlite":
        return SQLiteRunRepository(settings.sqlite_database_path)
    if backend == "mysql":
        return MySQLRunRepository(settings)
    raise ValueError(
        "AGENT_SERVICE_STORAGE_BACKEND 只能是 auto、sqlite 或 mysql"
    )
