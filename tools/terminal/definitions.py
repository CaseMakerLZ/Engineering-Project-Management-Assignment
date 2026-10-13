"""本地终端工具注册定义。"""

from functools import partial
from pathlib import Path
import threading

from tools.registry import ToolDefinition

from .params import RunCommandArgs, RunShellArgs
from .service import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    TerminalAuthorizer,
    run_command,
    run_shell,
)


def build_terminal_tools(
    workspace_root: str | Path,
    *,
    authorizer: TerminalAuthorizer,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    concurrency_limit: threading.Semaphore | None = None,
    cancel_event: threading.Event | None = None,
) -> list[ToolDefinition]:
    """由本地宿主提供授权策略和项目工作区；模型只能给出操作意图。"""

    common = {
        "workspace_root": workspace_root,
        "authorizer": authorizer,
        "timeout_seconds": timeout_seconds,
        "max_output_bytes": max_output_bytes,
        "concurrency_limit": concurrency_limit,
        "cancel_event": cancel_event,
    }
    return [
        ToolDefinition(
            name="run_command",
            description="在当前本地项目目录执行一个程序及参数，不解释 Shell 语法；需用户授权。",
            args_model=RunCommandArgs,
            function=partial(run_command, **common),
        ),
        ToolDefinition(
            name="run_shell",
            description="在当前本地项目目录执行需要管道、重定向等语法的 Shell 命令；需用户授权。",
            args_model=RunShellArgs,
            function=partial(run_shell, **common),
        ),
    ]
