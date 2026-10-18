import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"

# Python 服务启动时需要的配置。环境变量可以覆盖这里的默认值。
@dataclass(frozen=True, slots=True)
class Settings:
    service_name: str = "python-agent-service"
    # LLM 配置与数据库、运行模式配置统一由 Settings 管理。
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model_id: str | None = None
    llm_timeout_seconds: float = 200.0
    web_api_key: str | None = None
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "agent_javabackend"
    internal_token: str | None = None
    max_prompt_length: int = 20_000
    # 本地实例显式绑定一个业务项目 ID 和任意位置的目录；云端使用受控父目录。
    execution_mode: str = "local"
    local_project_id: str | None = None
    local_project_root: str | None = None
    workspace_root: str = "."

    @classmethod
    def from_environment(cls) -> "Settings":
        # 显式读取项目根目录配置，避免依赖 PyCharm 的工作目录或调试环境。
        # override=False 保证真正的系统环境变量优先于本地 .env 文件。
        load_dotenv(dotenv_path=ENV_FILE, override=False)

        # 只在这里读取环境变量，其他代码直接使用 Settings 中的值。
        token = os.getenv("AGENT_SERVICE_INTERNAL_TOKEN") or None
        workspace_root = os.getenv(
            "AGENT_SERVICE_WORKSPACE_ROOT",
            ".",
        )
        local_project_root = os.getenv("AGENT_SERVICE_PROJECT_ROOT") or None
        return cls(
            service_name=os.getenv("AGENT_SERVICE_NAME", "python-agent-service"),
            llm_api_key=os.getenv("LLM_API_KEY") or None,
            llm_base_url=os.getenv("LLM_BASE_URL") or None,
            llm_model_id=os.getenv("LLM_MODEL_ID") or None,
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "200")),
            # 保留现有 SERPAPI_API_KEY 名称，避免改变已有本地配置；
            # 该值由服务端绑定给网络工具，不会进入模型参数。
            web_api_key=os.getenv("SERPAPI_API_KEY") or None,
            mysql_host=os.getenv("AGENT_SERVICE_MYSQL_HOST", "127.0.0.1"),
            mysql_port=int(os.getenv("AGENT_SERVICE_MYSQL_PORT", "3306")),
            mysql_user=os.getenv("AGENT_SERVICE_MYSQL_USER", "root"),
            mysql_password=os.getenv("AGENT_SERVICE_MYSQL_PASSWORD", "123456"),
            mysql_database=os.getenv("AGENT_SERVICE_MYSQL_DATABASE", "agent_javabackend"),
            internal_token=token,
            max_prompt_length=int(os.getenv("AGENT_SERVICE_MAX_PROMPT_LENGTH", "20000")),
            execution_mode=os.getenv("AGENT_SERVICE_EXECUTION_MODE", "local").lower(),
            local_project_id=os.getenv("AGENT_SERVICE_PROJECT_ID") or None,
            local_project_root=local_project_root,
            workspace_root=workspace_root,
        )
