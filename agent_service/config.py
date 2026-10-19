import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 使用环境中的 tomli 读取 TOML。
    import tomli as tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = PROJECT_ROOT / "config.toml"


@dataclass(frozen=True, slots=True)
class LocalProjectConfig:
    """TOML 中一个本地项目的最小配置。"""

    root: str
    name: str | None = None
    enabled: bool = True


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
    # auto 会根据运行模式选择本地 SQLite 或云端 MySQL，也可显式指定后端。
    storage_backend: str = "auto"
    sqlite_database_path: str = "data/agent.sqlite3"
    internal_token: str | None = None
    max_prompt_length: int = 20_000
    # 本地项目由 TOML 的 key 映射到真实目录；project_id 仍作为运行和日志归属标识。
    local_projects: dict[str, LocalProjectConfig] = field(default_factory=dict)
    # 兼容旧的 Settings 构造方式；新的本地配置使用 local_projects。
    local_project_id: str | None = None
    local_project_root: str | None = None
    # 云端使用受控父目录，项目目录由 project_id 选择。
    workspace_root: str = "."
    execution_mode: str = "local"

    @classmethod
    def from_environment(cls, config_path: str | Path | None = None) -> "Settings":
        """读取 TOML 主配置，系统环境变量只作为缺省回退。

        TOML 中已经明确配置的值优先于环境变量，避免本地项目路径和数据库
        文件位置因为 PyCharm 启动配置的残留值而悄悄改变。
        """
        selected_config = Path(config_path) if config_path is not None else Path(
            os.getenv("AGENT_SERVICE_CONFIG_FILE", CONFIG_FILE)
        )
        selected_config = selected_config.expanduser().resolve()
        toml_values = _load_toml(selected_config)
        environment_fallback: dict[str, str] = {}

        service = _section(toml_values, "service")
        llm = _section(toml_values, "llm")
        web = _section(toml_values, "web")
        mysql = _section(toml_values, "mysql")
        storage = _section(toml_values, "storage")
        runtime = _section(toml_values, "runtime")
        cloud = _section(toml_values, "cloud")
        local_projects = _load_local_projects(
            _section(toml_values, "local"), selected_config.parent
        )

        execution_mode = _string_setting(
            "AGENT_SERVICE_EXECUTION_MODE", runtime.get("mode"), environment_fallback, "local"
        ).lower()
        legacy_project_id = _optional_string_setting(
            "AGENT_SERVICE_PROJECT_ID", None, environment_fallback
        )
        legacy_project_root = _optional_string_setting(
            "AGENT_SERVICE_PROJECT_ROOT", None, environment_fallback
        )

        workspace_value = cloud.get("workspace_root", runtime.get("workspace_root"))
        workspace_root = _path_setting(
            "AGENT_SERVICE_WORKSPACE_ROOT", workspace_value, environment_fallback, ".", selected_config.parent
        )
        sqlite_database_path = _path_setting(
            "AGENT_SERVICE_SQLITE_DATABASE", storage.get("path"), environment_fallback,
            "data/agent.sqlite3", selected_config.parent
        )

        return cls(
            service_name=_string_setting(
                "AGENT_SERVICE_NAME", service.get("name"), environment_fallback, "python-agent-service"
            ),
            llm_api_key=_optional_string_setting("LLM_API_KEY", llm.get("api_key"), environment_fallback),
            llm_base_url=_optional_string_setting("LLM_BASE_URL", llm.get("base_url"), environment_fallback),
            llm_model_id=_optional_string_setting("LLM_MODEL_ID", llm.get("model_id"), environment_fallback),
            llm_timeout_seconds=_float_setting(
                "LLM_TIMEOUT_SECONDS", llm.get("timeout_seconds"), environment_fallback, 200.0
            ),
            web_api_key=_optional_string_setting("SERPAPI_API_KEY", web.get("api_key"), environment_fallback),
            mysql_host=_string_setting("AGENT_SERVICE_MYSQL_HOST", mysql.get("host"), environment_fallback, "127.0.0.1"),
            mysql_port=_int_setting("AGENT_SERVICE_MYSQL_PORT", mysql.get("port"), environment_fallback, 3306),
            mysql_user=_string_setting("AGENT_SERVICE_MYSQL_USER", mysql.get("user"), environment_fallback, "root"),
            mysql_password=_string_setting("AGENT_SERVICE_MYSQL_PASSWORD", mysql.get("password"), environment_fallback, "123456"),
            mysql_database=_string_setting(
                "AGENT_SERVICE_MYSQL_DATABASE", mysql.get("database"), environment_fallback, "agent_javabackend"
            ),
            storage_backend=_string_setting(
                "AGENT_SERVICE_STORAGE_BACKEND", storage.get("backend"), environment_fallback, "auto"
            ).lower(),
            sqlite_database_path=sqlite_database_path,
            internal_token=_optional_string_setting(
                "AGENT_SERVICE_INTERNAL_TOKEN", service.get("internal_token"), environment_fallback
            ),
            max_prompt_length=_int_setting(
                "AGENT_SERVICE_MAX_PROMPT_LENGTH", service.get("max_prompt_length"), environment_fallback, 20_000
            ),
            local_projects=local_projects,
            local_project_id=None if local_projects else legacy_project_id,
            local_project_root=None if local_projects else _resolve_path(
                legacy_project_root, selected_config.parent
            ),
            workspace_root=workspace_root,
            execution_mode=execution_mode,
        )


def _load_toml(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        return {}
    with config_path.open("rb") as file:
        values = tomllib.load(file)
    if not isinstance(values, dict):
        raise ValueError(f"TOML 配置文件必须是对象：{config_path}")
    return values


def _section(values: dict[str, Any], name: str) -> dict[str, Any]:
    section = values.get(name, {})
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ValueError(f"TOML 配置段 [{name}] 必须是表")
    return section


def _load_local_projects(local: dict[str, Any], config_dir: Path) -> dict[str, LocalProjectConfig]:
    projects = local.get("projects", {})
    if not isinstance(projects, dict):
        raise ValueError("[local.projects] 必须是项目表")

    result: dict[str, LocalProjectConfig] = {}
    for project_id, raw in projects.items():
        if not isinstance(project_id, str) or not isinstance(raw, dict):
            raise ValueError("每个本地项目必须使用 [local.projects.<project_id>] 配置")
        root = raw.get("root")
        if not isinstance(root, str) or not root.strip():
            raise ValueError(f"本地项目 {project_id!r} 必须配置 root")
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"本地项目 {project_id!r} 的 enabled 必须是布尔值")
        name = raw.get("name")
        if name is not None and not isinstance(name, str):
            raise ValueError(f"本地项目 {project_id!r} 的 name 必须是字符串")
        result[project_id] = LocalProjectConfig(
            root=_resolve_path(root, config_dir), name=name, enabled=enabled
        )
    return result


def _resolve_path(value: str | None, base_dir: Path) -> str | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return str(path.resolve())


def _environment_value(name: str, legacy_env: dict[str, str]) -> str | None:
    if name in os.environ:
        return os.environ[name]
    return legacy_env.get(name)


def _string_setting(name: str, toml_value: Any, legacy_env: dict[str, str], default: str) -> str:
    value = toml_value if toml_value is not None else _environment_value(name, legacy_env)
    return default if value is None or value == "" else str(value)


def _optional_string_setting(name: str, toml_value: Any, legacy_env: dict[str, str]) -> str | None:
    value = toml_value if toml_value is not None else _environment_value(name, legacy_env)
    return None if value is None or value == "" else str(value)


def _int_setting(name: str, toml_value: Any, legacy_env: dict[str, str], default: int) -> int:
    value = toml_value if toml_value is not None else _environment_value(name, legacy_env)
    return default if value is None or value == "" else int(value)


def _float_setting(name: str, toml_value: Any, legacy_env: dict[str, str], default: float) -> float:
    value = toml_value if toml_value is not None else _environment_value(name, legacy_env)
    return default if value is None or value == "" else float(value)


def _path_setting(
    name: str, toml_value: Any, legacy_env: dict[str, str], default: str, config_dir: Path
) -> str:
    value = toml_value if toml_value is not None else _environment_value(name, legacy_env)
    resolved = _resolve_path(str(value) if value not in (None, "") else default, config_dir)
    assert resolved is not None
    return resolved
