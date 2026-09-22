import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .domain import MessageRecord, RunRecord, RunStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _encode_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _decode_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SQLiteRunRepository:
    """Durable local repository. It can later be replaced by a PostgreSQL adapter."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    prompt TEXT NOT NULL,
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

    def create_run(self, run: RunRecord) -> RunRecord:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs
                (run_id, project_id, prompt, status, result, error,
                 created_at, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.project_id,
                    run.prompt,
                    run.status.value,
                    run.result,
                    run.error,
                    _encode_datetime(run.created_at),
                    _encode_datetime(run.started_at),
                    _encode_datetime(run.finished_at),
                ),
            )
        return run

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
            prompt=row["prompt"],
            status=RunStatus(row["status"]),
            result=row["result"],
            error=row["error"],
            created_at=_decode_datetime(row["created_at"]),
            started_at=_decode_datetime(row["started_at"]),
            finished_at=_decode_datetime(row["finished_at"]),
        )

    def update_run(self, run: RunRecord) -> RunRecord:
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

