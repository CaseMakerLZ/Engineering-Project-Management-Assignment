import os
from dataclasses import dataclass

# Python 服务启动时需要的配置。环境变量可以覆盖这里的默认值。
@dataclass(frozen=True, slots=True)
class Settings:
    service_name: str = "python-agent-service"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "agent_javabackend"
    internal_token: str | None = None
    max_prompt_length: int = 20_000
    workspace_root: str = "."

    @classmethod
    def from_environment(cls) -> "Settings":
        # 只在这里读取环境变量，其他代码直接使用 Settings 中的值。
        token = os.getenv("AGENT_SERVICE_INTERNAL_TOKEN") or None
        workspace_root = os.getenv(
            "AGENT_SERVICE_WORKSPACE_ROOT",
            ".",
        )
        return cls(
            mysql_host=os.getenv("AGENT_SERVICE_MYSQL_HOST", "127.0.0.1"),
            mysql_port=int(os.getenv("AGENT_SERVICE_MYSQL_PORT", "3306")),
            mysql_user=os.getenv("AGENT_SERVICE_MYSQL_USER", "root"),
            mysql_password=os.getenv("AGENT_SERVICE_MYSQL_PASSWORD", "123456"),
            mysql_database=os.getenv("AGENT_SERVICE_MYSQL_DATABASE", "agent_javabackend"),
            internal_token=token,
            workspace_root=workspace_root,
        )
