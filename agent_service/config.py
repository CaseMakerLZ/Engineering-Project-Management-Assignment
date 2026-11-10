import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from agent.state import DEFAULT_MAX_STEPS

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 使用环境中的 tomli 读取 TOML。
    import tomli as tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = PROJECT_ROOT / "config.toml"


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
    # 只限制 Python 的 MySQL 连接数，不与 Java 共用；实际使用时才建立连接。
    mysql_pool_size: int = 5
    mysql_connect_timeout_seconds: int = 5
    mysql_read_timeout_seconds: int = 10
    mysql_write_timeout_seconds: int = 10
    # auto 会根据运行模式选择本地 SQLite 或云端 MySQL，也可显式指定后端。
    storage_backend: str = "auto"
    sqlite_database_path: str = "data/agent.sqlite3"
    internal_token: str | None = None
    max_prompt_length: int = 20_000
    # 云端使用受控父目录，项目目录由 project_id 选择。
    workspace_root: str = "."
    execution_mode: str = "local"
    # 单个 Python 进程允许同时运行的 Agent 数量；满载时直接拒绝新任务，不建立无限等待队列。
    max_concurrent_runs: int = 4
    # 一轮指一次模型请求；一轮返回多个工具时仍只计一次。
    max_agent_steps: int = DEFAULT_MAX_STEPS
    # 单次请求预算，十进制token；输入包含规则和工具定义，输出另外预留。
    context_model_tokens: int = 256_000
    context_max_input_tokens: int = 216_000
    context_trigger_ratio: float = 0.8
    context_target_tokens: int = 100_000
    context_max_output_tokens: int = 32_000
    context_summary_tokens: int = 4_000
    context_count_mode: str = "auto"
    context_encoding: str = "cl100k_base"
    # disabled=不装配终端；local=明确允许本机终端；cloud模式下必须另开测试开关。
    terminal_mode: str = "disabled"
    terminal_allow_cloud_host_test: bool = False
    # 云端容器未通过部署机验证前保持关闭。开启后无宿主命令回退。
    sandbox_enabled: bool = False
    sandbox_image: str = "python-agent-sandbox:1"
    sandbox_timeout_seconds: int = 60
    sandbox_memory_mb: int = 512
    sandbox_cpus: float = 1.0
    sandbox_pids: int = 64
    sandbox_disk_mb: int = 256
    sandbox_max_output_bytes: int = 65536
    sandbox_max_concurrent: int = 1
    # 目录浏览的服务端限制（组长说明 §4.1 的起步值）。
    # 每页默认 100、最大 200；单目录扫描上限 5000 项，达到即报错而不是截断。
    workspace_page_size: int = 100
    workspace_max_page_size: int = 200
    workspace_max_scan_entries: int = 5000
    # 文本预览上限（组长说明 §4.2 的起步值 1 MiB）；超限返回 413，不截断内容。
    workspace_max_preview_bytes: int = 1_048_576
    # 单文件下载上限与并发名额（组长说明 §4.3 的起步值 20 MiB）。
    # 名额满时立刻 429 受控拒绝，不进入无界排队。
    workspace_max_download_bytes: int = 20_971_520
    workspace_max_concurrent_downloads: int = 8
    # 项目 ZIP 的起步限制（组长说明 §4.4）：文件数、输入总量、ZIP 上限、准备超时、
    # 同时打包数量，以及临时目录（必须与项目目录分开，避免递归打包）。
    workspace_max_archive_files: int = 5000
    workspace_max_archive_input_bytes: int = 104_857_600
    workspace_max_archive_bytes: int = 104_857_600
    workspace_archive_timeout_seconds: float = 60.0
    workspace_max_concurrent_archives: int = 1
    workspace_archive_temp_dir: str = ""
    # Git 只用于云端项目版本，不开放任意命令或远程推送。
    workspace_git_timeout_seconds: float = 30.0
    workspace_git_max_output_bytes: int = 1_048_576
    workspace_git_max_file_bytes: int = 20_971_520

    def __post_init__(self) -> None:
        if (isinstance(self.max_agent_steps, bool)
                or not isinstance(self.max_agent_steps, int) or self.max_agent_steps < 1):
            raise ValueError("max_agent_steps 必须是正整数")
        if self.context_count_mode not in {"auto", "server", "estimate"}:
            raise ValueError("context.count_mode只能是auto、server或estimate")
        if not isinstance(self.context_encoding, str) or not self.context_encoding.strip():
            raise ValueError("context.encoding必须是非空字符串")
        values = (self.context_model_tokens, self.context_max_input_tokens,
                  self.context_target_tokens, self.context_max_output_tokens, self.context_summary_tokens)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values):
            raise ValueError("context的token预算必须是正整数")
        if (isinstance(self.context_trigger_ratio, bool)
                or not isinstance(self.context_trigger_ratio, (int, float))
                or not 0 < self.context_trigger_ratio < 1):
            raise ValueError("context.trigger_ratio必须在0和1之间")
        if self.context_max_input_tokens + self.context_max_output_tokens >= self.context_model_tokens:
            raise ValueError("context输入与输出预算之和必须小于模型容量")
        if not self.context_summary_tokens < self.context_target_tokens < self.context_max_input_tokens * self.context_trigger_ratio:
            raise ValueError("context必须满足：摘要上限 < 整理目标 < 触发线 < 输入上限")
        if not isinstance(self.sandbox_enabled, bool):
            raise ValueError("sandbox.enabled必须是布尔值")
        if self.terminal_mode not in {"disabled", "local"}:
            raise ValueError("terminal.mode只能是disabled或local")
        if not isinstance(self.terminal_allow_cloud_host_test, bool):
            raise ValueError("terminal.allow_cloud_host_test必须是布尔值")
        if isinstance(self.sandbox_max_concurrent, bool) or not isinstance(self.sandbox_max_concurrent, int) or not 1 <= self.sandbox_max_concurrent <= 4:
            raise ValueError("sandbox.max_concurrent必须是1到4的整数")
        from tools.terminal.sandbox import SandboxLimits
        SandboxLimits(image=self.sandbox_image, timeout_seconds=self.sandbox_timeout_seconds,
            memory_mb=self.sandbox_memory_mb, cpus=self.sandbox_cpus, pids=self.sandbox_pids,
            disk_mb=self.sandbox_disk_mb, max_output_bytes=self.sandbox_max_output_bytes)

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
        workspace = _section(toml_values, "workspace")
        context = _section(toml_values, "context")
        sandbox = _section(toml_values, "sandbox")
        terminal = _section(toml_values, "terminal")

        execution_mode = _string_setting(
            "AGENT_SERVICE_EXECUTION_MODE", runtime.get("mode"), environment_fallback, "local"
        ).lower()

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
            mysql_pool_size=_int_setting(
                "AGENT_SERVICE_MYSQL_POOL_SIZE", mysql.get("pool_size"), environment_fallback, 5
            ),
            mysql_connect_timeout_seconds=_int_setting(
                "AGENT_SERVICE_MYSQL_CONNECT_TIMEOUT_SECONDS", mysql.get("connect_timeout_seconds"),
                environment_fallback, 5,
            ),
            mysql_read_timeout_seconds=_int_setting(
                "AGENT_SERVICE_MYSQL_READ_TIMEOUT_SECONDS", mysql.get("read_timeout_seconds"),
                environment_fallback, 10,
            ),
            mysql_write_timeout_seconds=_int_setting(
                "AGENT_SERVICE_MYSQL_WRITE_TIMEOUT_SECONDS", mysql.get("write_timeout_seconds"),
                environment_fallback, 10,
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
            workspace_root=workspace_root,
            execution_mode=execution_mode,
            max_concurrent_runs=_int_setting(
                "AGENT_SERVICE_MAX_CONCURRENT_RUNS",
                runtime.get("max_concurrent_runs"),
                environment_fallback,
                4,
            ),
            max_agent_steps=_positive_steps_setting(runtime.get("max_agent_steps"), environment_fallback),
            context_model_tokens=_context_int(context, "model_tokens", 256_000),
            context_max_input_tokens=_context_int(context, "max_input_tokens", 216_000),
            context_target_tokens=_context_int(context, "target_tokens", 100_000),
            context_max_output_tokens=_context_int(context, "max_output_tokens", 32_000),
            context_summary_tokens=_context_int(context, "summary_tokens", 4_000),
            context_trigger_ratio=context.get("trigger_ratio", 0.8),
            context_count_mode=context.get("count_mode", "auto"),
            context_encoding=context.get("encoding", "cl100k_base"),
            terminal_mode=terminal.get("mode", "disabled"),
            terminal_allow_cloud_host_test=terminal.get("allow_cloud_host_test", False),
            sandbox_enabled=sandbox.get("enabled", False),
            sandbox_image=sandbox.get("image", "python-agent-sandbox:1"),
            sandbox_timeout_seconds=sandbox.get("timeout_seconds", 60),
            sandbox_memory_mb=sandbox.get("memory_mb", 512),
            sandbox_cpus=sandbox.get("cpus", 1.0),
            sandbox_pids=sandbox.get("pids", 64),
            sandbox_disk_mb=sandbox.get("disk_mb", 256),
            sandbox_max_output_bytes=sandbox.get("max_output_bytes", 65536),
            sandbox_max_concurrent=sandbox.get("max_concurrent", 1),
            workspace_page_size=_int_setting(
                "AGENT_SERVICE_WORKSPACE_PAGE_SIZE", workspace.get("page_size"), environment_fallback, 100
            ),
            workspace_max_page_size=_int_setting(
                "AGENT_SERVICE_WORKSPACE_MAX_PAGE_SIZE", workspace.get("max_page_size"), environment_fallback, 200
            ),
            workspace_max_scan_entries=_int_setting(
                "AGENT_SERVICE_WORKSPACE_MAX_SCAN_ENTRIES",
                workspace.get("max_scan_entries"), environment_fallback, 5000,
            ),
            workspace_max_preview_bytes=_int_setting(
                "AGENT_SERVICE_WORKSPACE_MAX_PREVIEW_BYTES",
                workspace.get("max_preview_bytes"), environment_fallback, 1_048_576,
            ),
            workspace_max_download_bytes=_int_setting(
                "AGENT_SERVICE_WORKSPACE_MAX_DOWNLOAD_BYTES",
                workspace.get("max_download_bytes"), environment_fallback, 20_971_520,
            ),
            workspace_max_concurrent_downloads=_int_setting(
                "AGENT_SERVICE_WORKSPACE_MAX_CONCURRENT_DOWNLOADS",
                workspace.get("max_concurrent_downloads"), environment_fallback, 8,
            ),
            workspace_max_archive_files=_int_setting(
                "AGENT_SERVICE_WORKSPACE_MAX_ARCHIVE_FILES",
                workspace.get("max_archive_files"), environment_fallback, 5000,
            ),
            workspace_max_archive_input_bytes=_int_setting(
                "AGENT_SERVICE_WORKSPACE_MAX_ARCHIVE_INPUT_BYTES",
                workspace.get("max_archive_input_bytes"), environment_fallback, 104_857_600,
            ),
            workspace_max_archive_bytes=_int_setting(
                "AGENT_SERVICE_WORKSPACE_MAX_ARCHIVE_BYTES",
                workspace.get("max_archive_bytes"), environment_fallback, 104_857_600,
            ),
            workspace_archive_timeout_seconds=_float_setting(
                "AGENT_SERVICE_WORKSPACE_ARCHIVE_TIMEOUT_SECONDS",
                workspace.get("archive_timeout_seconds"), environment_fallback, 60.0,
            ),
            workspace_max_concurrent_archives=_int_setting(
                "AGENT_SERVICE_WORKSPACE_MAX_CONCURRENT_ARCHIVES",
                workspace.get("max_concurrent_archives"), environment_fallback, 1,
            ),
            workspace_archive_temp_dir=_string_setting(
                "AGENT_SERVICE_WORKSPACE_ARCHIVE_TEMP_DIR",
                workspace.get("archive_temp_dir"), environment_fallback, "",
            ),
            workspace_git_timeout_seconds=_float_setting(
                "AGENT_SERVICE_GIT_TIMEOUT_SECONDS", workspace.get("git_timeout_seconds"),
                environment_fallback, 30.0,
            ),
            workspace_git_max_output_bytes=_int_setting(
                "AGENT_SERVICE_GIT_MAX_OUTPUT_BYTES", workspace.get("git_max_output_bytes"),
                environment_fallback, 1_048_576,
            ),
            workspace_git_max_file_bytes=_int_setting(
                "AGENT_SERVICE_GIT_MAX_FILE_BYTES", workspace.get("git_max_file_bytes"),
                environment_fallback, 20_971_520,
            ),
        )


def _context_int(section: dict, key: str, default: int) -> int:
    """上下文预算只从TOML读取，拒绝布尔/小数，不隐式截断为整数。"""
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"context.{key}必须是正整数")
    return value


def _positive_steps_setting(value: Any, environment_fallback: dict[str, str]) -> int:
    """轮数只接受正整数，不把 true、浮点数或零悄悄转换成有效配置。"""
    if value is None:
        value = _environment_value("AGENT_SERVICE_MAX_AGENT_STEPS", environment_fallback)
    if value is None or value == "":
        return DEFAULT_MAX_STEPS
    if isinstance(value, bool) or not (
        isinstance(value, int) or isinstance(value, str) and value.isdecimal()
    ):
        raise ValueError("max_agent_steps 必须是正整数")
    result = int(value)
    if result < 1:
        raise ValueError("max_agent_steps 必须是正整数")
    return result


def _load_toml(config_path: Path) -> dict[str, Any]:
    """读取 TOML 主配置；文件不存在返回空字典，不创建文件也不报错。"""

    if not config_path.is_file():
        return {}
    with config_path.open("rb") as file:
        values = tomllib.load(file)
    if not isinstance(values, dict):
        raise ValueError(f"TOML 配置文件必须是对象：{config_path}")
    return values


def _section(values: dict[str, Any], name: str) -> dict[str, Any]:
    """取出一个配置段；缺失或显式为空都当作空段，类型不对直接报错。"""

    section = values.get(name, {})
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ValueError(f"TOML 配置段 [{name}] 必须是表")
    return section


def _resolve_path(value: str | None, base_dir: Path) -> str | None:
    """把配置里的相对路径按配置文件所在目录解析成绝对路径。"""

    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return str(path.resolve())


def _environment_value(name: str, legacy_env: dict[str, str]) -> str | None:
    """取环境变量值；没有时回退到调用方传入的兼容映射。"""

    if name in os.environ:
        return os.environ[name]
    return legacy_env.get(name)


def _string_setting(name: str, toml_value: Any, legacy_env: dict[str, str], default: str) -> str:
    """读取字符串配置：TOML 优先，其次环境变量，最后默认值。"""

    value = toml_value if toml_value is not None else _environment_value(name, legacy_env)
    return default if value is None or value == "" else str(value)


def _optional_string_setting(name: str, toml_value: Any, legacy_env: dict[str, str]) -> str | None:
    """读取可为空的字符串配置；空串按未配置处理，返回 None。"""

    value = toml_value if toml_value is not None else _environment_value(name, legacy_env)
    return None if value is None or value == "" else str(value)


def _int_setting(name: str, toml_value: Any, legacy_env: dict[str, str], default: int) -> int:
    """读取整数配置；空值用默认值，非数字字符串会直接抛 ValueError。"""

    value = toml_value if toml_value is not None else _environment_value(name, legacy_env)
    return default if value is None or value == "" else int(value)


def _float_setting(name: str, toml_value: Any, legacy_env: dict[str, str], default: float) -> float:
    """读取浮点配置；空值用默认值，非数字字符串会直接抛 ValueError。"""

    value = toml_value if toml_value is not None else _environment_value(name, legacy_env)
    return default if value is None or value == "" else float(value)


def _path_setting(
    name: str, toml_value: Any, legacy_env: dict[str, str], default: str, config_dir: Path
) -> str:
    """读取路径配置并解析成绝对路径；相对路径以配置文件所在目录为基准。"""

    value = toml_value if toml_value is not None else _environment_value(name, legacy_env)
    resolved = _resolve_path(str(value) if value not in (None, "") else default, config_dir)
    assert resolved is not None
    return resolved
