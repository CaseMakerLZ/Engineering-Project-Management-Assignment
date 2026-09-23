import os
from dataclasses import dataclass
from pathlib import Path


# 服务运行所需的集中配置。正式部署时由环境变量覆盖敏感或环境相关值。
@dataclass(frozen=True, slots=True)
class Settings:
    service_name: str = "python-agent-service"
    database_path: Path = Path("data/agent_service.sqlite3")
    internal_token: str | None = None
    max_prompt_length: int = 20_000

    @classmethod
    def from_environment(cls) -> "Settings":
        # 只在配置层读取环境变量，业务层不直接访问 os.environ。
        database_path = Path(
            os.getenv("AGENT_SERVICE_DB_PATH", "data/agent_service.sqlite3")
        )
        token = os.getenv("AGENT_SERVICE_INTERNAL_TOKEN") or None
        return cls(database_path=database_path, internal_token=token)
