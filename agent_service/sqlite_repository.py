"""SQLite 版 Agent 运行记录仓储。

这个仓储只负责本地运行模式下的持久化，不负责项目路径解析，也不负责
Agent 的上下文组装。它实现的接口与 repository.py 中的 RunRepository
保持一致，因此 RunService 不需要知道底层使用的是 SQLite 还是 MySQL。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from .domain import Run, RunMessage, RunStatus


class SQLiteRunRepository:
    """把 Agent 运行、上下文和过程消息保存到同一个 SQLite 文件。"""

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
    )

    def __init__(self, database_path: str | Path, *, timeout_seconds: float = 5.0) -> None:
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
        """幂等创建运行记录表和过程消息表。"""
        if self._initialized:
            return

        with self._connection_lock:
            if self._initialized:
                return
            connection = self._connect()
            # 兼容已经由 JSONL 版本创建的 agent_run：它缺少 context_json，
            # 但仍然可以通过一次本地结构升级继续使用同一个 SQLite 文件。
            connection.execute(self._schema[0])
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(agent_run)").fetchall()
            }
            if "context_json" not in columns:
                connection.execute(
                    "ALTER TABLE agent_run ADD COLUMN context_json TEXT NOT NULL DEFAULT '[]'"
                )
            connection.execute(self._schema[1])
            self._initialized = True

    def close(self) -> None:
        """关闭当前仓储复用的连接；关闭后再次使用会按需重新初始化。"""
        with self._connection_lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            self._initialized = False

    def create_run(self, run: Run) -> Run:
        """保存一条初始运行记录及其启动上下文。"""
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
        """按运行 ID 读取一条运行记录。"""
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
        """读取当前运行之前、同项目同对话的最近已完成轮次，按时间正序返回。"""
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

    def update_run(self, run: Run) -> Run:
        """更新运行状态、结果和时间字段。"""
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
        """保存本次运行真正注入 Agent 的初始上下文快照。"""
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
        """在一个短事务中追加消息并分配连续序号。"""
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
        """按运行内序号读取过程消息。"""
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
                    content=_decode_json(row["content_json"]),
                    created_at=_from_sqlite_datetime(row["created_at"]),
                )
                for row in rows
            ]


def _to_sqlite_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _from_sqlite_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    # Java OffsetDateTime.toString() 对 UTC 使用结尾 `Z`；Python 3.10 的
    # datetime.fromisoformat 只接受 `+00:00`，因此在解析前统一转换。
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _decode_json(value: str | None) -> Any:
    if value is None:
        return None
    return json.loads(value)


def _run_from_row(row: sqlite3.Row) -> Run:
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
