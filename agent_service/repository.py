"""把 Agent 运行数据保存到 MySQL。"""

import json
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Protocol

from .config import Settings
from .domain import Run, RunMessage, RunStatus
from .sqlite_repository import SQLiteRunRepository


def _decode_json(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list, int, float, bool)):
        return value
    return json.loads(value)


def _db_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class RunRepository(Protocol):
    """RunService 需要的数据保存功能。(接口)"""
    def initialize(self) -> None: ...
    def create_run(self, run: Run) -> Run: ...
    def get_run(self, run_id: str) -> Run | None: ...
    def update_run(self, run: Run) -> Run: ...
    def append_messages(self, run_id: str, messages: list[tuple[str, Any]]) -> None: ...
    def list_messages(self, run_id: str) -> list[RunMessage]: ...


class MySQLRunRepository:
    """Python 服务使用的 MySQL 数据保存实现。(上面接口的实现)"""

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
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._initialize_lock = Lock()
        self._initialized = False

    def _connect(self):
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

    def update_run(self, run: Run) -> Run:
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

    def append_messages(self, run_id: str, messages: list[tuple[str, Any]]) -> None:
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


def create_run_repository(settings: Settings) -> RunRepository:
    """根据配置创建本地或云端的运行记录仓储。
    云端/本地运行转化工厂
    选择逻辑集中在启动边界，RunService 仍然只依赖 RunRepository 接口。
    ``auto`` 是默认值：本地模式使用 SQLite，云端模式使用 MySQL。
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
