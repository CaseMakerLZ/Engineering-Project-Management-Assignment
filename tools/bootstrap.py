'''
这个类负责：

创建 ToolRegistry
    ↓
注册 filesystem 工具(finished)
    ↓
注册 web 工具
    ↓
注册 terminal 工具
    ↓
返回完整的 ToolRegistry
'''
from pathlib import Path
import re
import httpx
import threading

from tools.filesystem.definitions import build_filesystem_tools
from tools.web.definitions import build_web_tools
from tools.terminal.definitions import build_terminal_tools
from tools.terminal.service import TerminalAuthorizer, DEFAULT_TIMEOUT_SECONDS, DEFAULT_MAX_OUTPUT_BYTES
from tools.registry import ToolRegistry
from tools.exceptions import ToolError, ToolErrorCode


def create_default_registry(
    workspace_root: str | Path | None = None,
    project_id: str | None = None,
    *,
    web_api_key: str | None = None,
    web_search_endpoint: str = "https://api.tavily.com/search",
    web_timeout_seconds: float = 10.0,
    web_max_response_bytes: int = 2 * 1024 * 1024,
    web_max_redirects: int = 3,
    web_http_client: httpx.Client | None = None,
    local_terminal_enabled: bool = False,
    local_terminal_authorizer: TerminalAuthorizer | None = None,
    local_terminal_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    local_terminal_max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    local_terminal_concurrency_limit: threading.Semaphore | None = None,
    local_terminal_cancel_event: threading.Event | None = None,
) -> ToolRegistry:
    """创建绑定到一个项目目录的工具注册表。

    workspace_root 是所有项目目录的父目录；project_id 对应其中一个子目录。
    """
    root = Path(workspace_root) if workspace_root is not None else Path.cwd()
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "工作区根目录不存在或不是目录")

    if project_id is not None:
        # Java 当前使用 UUID。限制为可移植的单层目录名，避免 Windows/Linux 路径解释不同。
        if not re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
            raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "project_id 只能包含字母、数字、下划线和连字符")
        project_path = root / project_id
        if project_path.is_symlink():
            raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "项目工作区不能是符号链接")
        project_root = project_path.resolve()
        if not project_root.is_relative_to(root) or not project_root.is_dir():
            raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "项目工作区不存在或不在工作区根目录内")
    else:
        # 本地调试模式：未指定 project_id 时，workspace_root 本身是当前工作区。
        project_root = root

    registry = ToolRegistry()
    for tool in build_filesystem_tools(project_root):
        registry.register(tool)
    for tool in build_web_tools(
        api_key=web_api_key,
        search_endpoint=web_search_endpoint,
        timeout_seconds=web_timeout_seconds,
        max_response_bytes=web_max_response_bytes,
        max_redirects=web_max_redirects,
        http_client=web_http_client,
    ):
        registry.register(tool)
    if local_terminal_enabled:
        if local_terminal_authorizer is None:
            raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地终端工具需要服务端授权回调")
        for tool in build_terminal_tools(
            project_root,
            authorizer=local_terminal_authorizer,
            timeout_seconds=local_terminal_timeout_seconds,
            max_output_bytes=local_terminal_max_output_bytes,
            concurrency_limit=local_terminal_concurrency_limit,
            cancel_event=local_terminal_cancel_event,
        ):
            registry.register(tool)
    return registry
