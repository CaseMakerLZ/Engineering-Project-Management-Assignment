import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .domain import MessageRecord, RunRecord, RunStatus

#返回当前 UTC 时间
def _now() -> datetime:
    return datetime.now(timezone.utc)

#把 datetime 转成 ISO 格式字符串，用于写入 SQLite。
def _encode_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None

#把 SQLite 中的 ISO 字符串恢复为 datetime 对象
def _decode_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SQLiteRunRepository:
    """Durable local repository. It can later be replaced by a PostgreSQL adapter."""

    def __init__(self, database_path: Path) -> None:
        # SQLite 作为第一版持久化实现，接口保持独立，便于未来替换 PostgreSQL。
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        # 每次操作独立连接，避免把 SQLite Connection 泄漏到业务层。
        connection = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        return connection

    #创建runs表与messages表
    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    conversation_id TEXT,
                    prompt TEXT NOT NULL,
                    context_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    message_type TEXT NOT NULL,
                    content_json TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, sequence),
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_run_id
                    ON messages(run_id, sequence);
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(runs)")}
            if "conversation_id" not in columns:
                connection.execute("ALTER TABLE runs ADD COLUMN conversation_id TEXT")
            if "context_json" not in columns:
                connection.execute("ALTER TABLE runs ADD COLUMN context_json TEXT NOT NULL DEFAULT '[]'")

    #向 runs 表插入一条新的任务记录。
    def create_run(self, run: RunRecord) -> RunRecord:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs
                (run_id, project_id, conversation_id, prompt, context_json, status, result, error,
                 created_at, started_at, finished_at)
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
                    _encode_datetime(run.created_at),
                    _encode_datetime(run.started_at),
                    _encode_datetime(run.finished_at),
                ),
            )
        return run

    #根据 run_id 查询任务。如果找到了，就把 SQLite 行转换成 RunRecord；否则返回 None。
    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        return RunRecord(
            run_id=row["run_id"],
            project_id=row["project_id"],
            conversation_id=row["conversation_id"],
            prompt=row["prompt"],
            context=json.loads(row["context_json"]),
            status=RunStatus(row["status"]),
            result=row["result"],
            error=row["error"],
            created_at=_decode_datetime(row["created_at"]),
            started_at=_decode_datetime(row["started_at"]),
            finished_at=_decode_datetime(row["finished_at"]),
        )

    def update_run(self, run: RunRecord) -> RunRecord:
        # 状态、结果和时间戳统一更新，保证一次状态变化的数据完整性。
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE runs SET status = ?, result = ?, error = ?,
                    started_at = ?, finished_at = ?
                WHERE run_id = ?
                """,
                (
                    run.status.value,
                    run.result,
                    run.error,
                    _encode_datetime(run.started_at),
                    _encode_datetime(run.finished_at),
                    run.run_id,
                ),
            )
        return run

    def append_messages(
        self,
        run_id: str,
        messages: list[tuple[str, dict[str, Any] | str | None]],
    ) -> None:
        '''
            把一批消息追加到指定任务下。
            关键点：
            先查询当前任务已有消息的最大 sequence；
            从最大值后面继续编号；
            把每条消息的 content 转成 JSON；
            批量插入数据库。
            这样即使分多次保存消息，也能保证同一个 run_id 下序号连续递增。
        '''
        if not messages:
            return
        with self._lock, self._connect() as connection:
            current = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM messages WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            rows = []
            for offset, (message_type, content) in enumerate(messages, start=1):
                rows.append(
                    (
                        run_id,
                        current + offset,
                        message_type,
                        json.dumps(content, ensure_ascii=False),
                        _encode_datetime(_now()),
                    )
                )
            connection.executemany(
                """
                INSERT INTO messages
                (run_id, sequence, message_type, content_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
    #按 sequence 从小到大查询某个任务的所有消息，并转换成 MessageRecord 列表。
    def list_messages(self, run_id: str) -> list[MessageRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sequence, message_type, content_json, created_at
                FROM messages WHERE run_id = ? ORDER BY sequence
                """,
                (run_id,),
            ).fetchall()
        return [
            MessageRecord(
                sequence=row["sequence"],
                message_type=row["message_type"],
                content=json.loads(row["content_json"])
                if row["content_json"] is not None
                else None,
                created_at=_decode_datetime(row["created_at"]),
            )
            for row in rows
        ]
