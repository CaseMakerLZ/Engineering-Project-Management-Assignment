import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    service_name: str = "python-agent-service"
    database_path: Path = Path("data/agent_service.sqlite3")
    internal_token: str | None = None
    max_prompt_length: int = 20_000

    @classmethod
    def from_environment(cls) -> "Settings":
        database_path = Path(
            os.getenv("AGENT_SERVICE_DB_PATH", "data/agent_service.sqlite3")
        )
        token = os.getenv("AGENT_SERVICE_INTERNAL_TOKEN") or None
        return cls(database_path=database_path, internal_token=token)

