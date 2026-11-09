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
            description="在当前项目目录执行一个程序及参数，不解释Shell语法。仅在服务端明确开启本地终端时可用；Office任务可用python调用python-docx、openpyxl、pypdf和reportlab（以实际导入结果为准）。生成Word应输出真正的.docx，不要把HTML改名为.doc。",
            args_model=RunCommandArgs,
            function=partial(run_command, **common),
        ),
        ToolDefinition(
            name="run_shell",
            description="在当前项目目录执行需要管道、重定向等语法的Shell命令。仅在服务端明确开启本地终端时可用；命令结束后应检查exit_code和输出。",
            args_model=RunShellArgs,
            function=partial(run_shell, **common),
        ),
    ]


def build_sandbox_tools(executor) -> list[ToolDefinition]:
    """模型沿用命令参数；真实副本、镜像和权限都只由服务端装配。"""
    return [
        ToolDefinition(name="run_command", args_model=RunCommandArgs,
            description="在本次任务专用的Linux环境执行程序及参数，多次调用共享临时文件和依赖。网络关闭，无宿主路径/端口；非零exit_code需检查。已提供Python数据与Office库，以及Three.js、Vite、TypeScript、esbuild；后台程序在每条命令结束时停止。",
            function=executor.run_command),
        ToolDefinition(name="run_shell", args_model=RunShellArgs,
            description="在本次任务专用的Linux环境执行/bin/sh命令，可用管道/重定向。多次调用共享任务内临时依赖，但任务结束后删除且不写回node_modules或.venv。网络关闭，不能访问其他用户或服务器目录；可在同一命令内启动服务、自测并退出。",
            function=executor.run_shell),
    ]
