"""本地 Windows/Linux 终端执行。

这不是沙箱：工作目录和精简环境只能降低意外影响，任意程序或 Shell
仍可能访问项目外资源。是否执行由服务端授权回调决定。
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import threading
import time
from typing import Callable

from .TerminalToolExecutionOutput import RunCommandOutput, RunShellOutput
from .exception import TerminalErrorCode, TerminalToolError
from .params import MAX_ARGUMENTS, MAX_ARGUMENT_LENGTH, MAX_ARGUMENTS_LENGTH, MAX_COMMAND_LENGTH
from tools.executor import current_tool_cancellation


DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024
MAX_TIMEOUT_SECONDS = 300.0
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
_DEFAULT_CONCURRENCY_LIMIT = threading.BoundedSemaphore(2)


@dataclass(frozen=True)
class TerminalRequest:
    """展示给本地授权层的完整操作，不包含模型可更改的权限字段。"""

    tool: str
    workspace: Path
    program: str | None = None
    args: tuple[str, ...] = ()
    command: str | None = None
    shell: str | None = None


TerminalAuthorizer = Callable[[TerminalRequest], bool]


def _check_limits(timeout_seconds: float, max_output_bytes: int) -> None:
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise TerminalToolError(TerminalErrorCode.RESOURCE_LIMIT, "终端超时时间配置无效")
    if not isinstance(max_output_bytes, int) or not 0 < max_output_bytes <= MAX_OUTPUT_BYTES:
        raise TerminalToolError(TerminalErrorCode.RESOURCE_LIMIT, "终端输出大小配置无效")


def _workspace(workspace_root: str | Path) -> Path:
    given = Path(workspace_root).expanduser()
    if given.is_symlink():
        raise TerminalToolError(TerminalErrorCode.WORKSPACE_ERROR, "项目工作目录不能是符号链接")
    root = given.resolve()
    if not root.is_dir():
        raise TerminalToolError(TerminalErrorCode.WORKSPACE_ERROR, "项目工作目录不存在")
    return root


def _authorize(request: TerminalRequest, authorizer: TerminalAuthorizer | None) -> None:
    if authorizer is None:
        raise TerminalToolError(TerminalErrorCode.APPROVAL_REQUIRED, "终端操作需要用户授权")
    try:
        allowed = authorizer(request)
    except Exception as exc:
        raise TerminalToolError(TerminalErrorCode.APPROVAL_REQUIRED, "无法确认终端操作授权", cause=exc) from exc
    if allowed is not True:
        raise TerminalToolError(TerminalErrorCode.DENIED, "用户未授权此终端操作")


def _environment() -> dict[str, str]:
    """只传入常见运行时变量，不继承服务端密钥。"""

    allowed = {
        "PATH", "PATHEXT", "SystemRoot", "SYSTEMROOT", "ComSpec", "COMSPEC",
        "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "LANG", "LC_ALL",
        "JAVA_HOME", "CONDA_PREFIX", "CONDA_DEFAULT_ENV",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


def _shell_argv(system: str, command: str) -> tuple[list[str], str]:
    if system == "Windows":
        shell = shutil.which("pwsh") or shutil.which("powershell.exe")
        if shell is None:
            raise TerminalToolError(TerminalErrorCode.PROCESS_START_FAILED, "找不到本地 PowerShell")
        return [shell, "-NoProfile", "-NonInteractive", "-Command", command], "powershell"
    shell = "/bin/sh"
    if not Path(shell).is_file():
        raise TerminalToolError(TerminalErrorCode.PROCESS_START_FAILED, "找不到本地 Shell")
    return [shell, "-c", command], "sh"


def _stop_process_tree(process: subprocess.Popen[bytes], system: str) -> None:
    """超时、取消和超量输出时尽力清理进程树。"""

    if system == "Linux":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        # CREATE_NEW_PROCESS_GROUP 本身不保证子进程随父进程退出。
        # taskkill /T /F 用 PID 定位已启动的进程树，不执行模型提供的命令。
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run(
    argv: list[str],
    *,
    workspace: Path,
    timeout_seconds: float,
    max_output_bytes: int,
    cancel_event: threading.Event | None,
    concurrency_limit: threading.Semaphore | None,
) -> tuple[int, str, str, int]:
    system = platform.system()
    if system not in {"Windows", "Linux"}:
        raise TerminalToolError(TerminalErrorCode.UNSUPPORTED_PLATFORM, "终端工具只支持 Windows 和 Linux")
    _check_limits(timeout_seconds, max_output_bytes)
    ambient_cancel = current_tool_cancellation()
    if (cancel_event is not None and cancel_event.is_set()) or (ambient_cancel is not None and ambient_cancel.is_set()):
        raise TerminalToolError(TerminalErrorCode.CANCELLED, "终端操作已取消")
    limit = concurrency_limit or _DEFAULT_CONCURRENCY_LIMIT
    if not limit.acquire(blocking=False):
        raise TerminalToolError(TerminalErrorCode.RESOURCE_LIMIT, "终端并发数量已达上限")

    process: subprocess.Popen[bytes] | None = None
    try:
        kwargs: dict = {"start_new_session": True} if system == "Linux" else {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
        }
        try:
            process = subprocess.Popen(
                argv,
                cwd=workspace,
                env=_environment(),
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **kwargs,
            )
        except (OSError, ValueError) as exc:
            raise TerminalToolError(TerminalErrorCode.PROCESS_START_FAILED, "终端进程无法启动", cause=exc) from exc

        output = {"stdout": bytearray(), "stderr": bytearray()}
        output_lock = threading.Lock()
        output_limit_hit = threading.Event()
        reader_errors: list[OSError] = []

        def read_pipe(label: str, pipe) -> None:
            try:
                while True:
                    chunk = pipe.read(4096)
                    if not chunk:
                        break
                    with output_lock:
                        available = max_output_bytes - sum(len(value) for value in output.values())
                        output[label].extend(chunk[:max(available, 0)])
                        if len(chunk) > available:
                            output_limit_hit.set()
                            break
            except OSError as exc:
                reader_errors.append(exc)
            finally:
                pipe.close()

        readers = [
            threading.Thread(target=read_pipe, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=read_pipe, args=("stderr", process.stderr), daemon=True),
        ]
        for reader in readers:
            reader.start()

        started = time.monotonic()
        failure: TerminalToolError | None = None
        try:
            while process.poll() is None or any(reader.is_alive() for reader in readers):
                if (cancel_event is not None and cancel_event.is_set()) or (ambient_cancel is not None and ambient_cancel.is_set()):
                    failure = TerminalToolError(TerminalErrorCode.CANCELLED, "终端操作已取消")
                    break
                if output_limit_hit.is_set():
                    failure = TerminalToolError(TerminalErrorCode.OUTPUT_LIMIT, "终端输出超过大小限制")
                    break
                if time.monotonic() - started >= timeout_seconds:
                    failure = TerminalToolError(TerminalErrorCode.TIMEOUT, "终端进程执行超时")
                    break
                time.sleep(0.01)
            # 进程和读取线程可能在同一次检查之间结束；结束后仍要检查输出上限。
            if failure is None and output_limit_hit.is_set():
                failure = TerminalToolError(TerminalErrorCode.OUTPUT_LIMIT, "终端输出超过大小限制")
            if failure is not None:
                _stop_process_tree(process, system)
            else:
                process.wait()
            for reader in readers:
                reader.join(timeout=1)
            if failure is not None:
                raise failure
            if reader_errors:
                raise TerminalToolError(TerminalErrorCode.RESOURCE_LIMIT, "终端输出读取失败", cause=reader_errors[0])
            return (
                int(process.returncode),
                bytes(output["stdout"]).decode("utf-8", errors="replace"),
                bytes(output["stderr"]).decode("utf-8", errors="replace"),
                int((time.monotonic() - started) * 1000),
            )
        finally:
            if process.poll() is None:
                _stop_process_tree(process, system)
    finally:
        limit.release()


def run_command(
    program: str,
    args: list[str] | None = None,
    *,
    workspace_root: str | Path,
    authorizer: TerminalAuthorizer | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    concurrency_limit: threading.Semaphore | None = None,
    cancel_event: threading.Event | None = None,
) -> RunCommandOutput:
    """在本地项目目录中运行单个程序，始终使用 shell=False。"""

    if not isinstance(program, str) or not program.strip() or "\x00" in program or len(program) > MAX_ARGUMENT_LENGTH:
        raise TerminalToolError(TerminalErrorCode.INVALID_ARGUMENT, "program 无效")
    args = [] if args is None else args
    if not isinstance(args, list) or len(args) > MAX_ARGUMENTS or any(not isinstance(item, str) for item in args):
        raise TerminalToolError(TerminalErrorCode.INVALID_ARGUMENT, "args 无效或超过长度限制")
    if sum(len(item) for item in args) > MAX_ARGUMENTS_LENGTH:
        raise TerminalToolError(TerminalErrorCode.INVALID_ARGUMENT, "args 总长度超过限制")
    if any("\x00" in item or len(item) > MAX_ARGUMENT_LENGTH for item in args):
        raise TerminalToolError(TerminalErrorCode.INVALID_ARGUMENT, "args 包含无效参数")
    workspace = _workspace(workspace_root)
    _authorize(TerminalRequest("run_command", workspace, program=program, args=tuple(args)), authorizer)
    exit_code, stdout, stderr, duration_ms = _run(
        [program, *args], workspace=workspace, timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes, cancel_event=cancel_event,
        concurrency_limit=concurrency_limit,
    )
    return RunCommandOutput(
        program=program, args=args, exit_code=exit_code, stdout=stdout,
        stderr=stderr, duration_ms=duration_ms, truncated=False,
    )


def run_shell(
    command: str,
    *,
    workspace_root: str | Path,
    authorizer: TerminalAuthorizer | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    concurrency_limit: threading.Semaphore | None = None,
    cancel_event: threading.Event | None = None,
) -> RunShellOutput:
    """按当前操作系统选择本地 Shell；仅本地工具注册表可暴露此能力。"""

    if not isinstance(command, str) or not command.strip() or "\x00" in command or len(command) > MAX_COMMAND_LENGTH:
        raise TerminalToolError(TerminalErrorCode.INVALID_ARGUMENT, "command 无效")
    workspace = _workspace(workspace_root)
    system = platform.system()
    if system not in {"Windows", "Linux"}:
        raise TerminalToolError(TerminalErrorCode.UNSUPPORTED_PLATFORM, "终端工具只支持 Windows 和 Linux")
    argv, shell_name = _shell_argv(system, command)
    _authorize(TerminalRequest("run_shell", workspace, command=command, shell=shell_name), authorizer)
    exit_code, stdout, stderr, duration_ms = _run(
        argv, workspace=workspace, timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes, cancel_event=cancel_event,
        concurrency_limit=concurrency_limit,
    )
    return RunShellOutput(
        command=command, shell=shell_name, exit_code=exit_code, stdout=stdout,
        stderr=stderr, duration_ms=duration_ms, truncated=False,
    )
