"""一个 Agent 任务复用一个 Docker 容器，不挂载宿主路径，不自动拉取镜像。"""

import base64
from dataclasses import dataclass
import json
import math
import re
import shutil
import subprocess
import threading
import time
import uuid

from tools.executor import current_tool_cancellation
from agent_service.workspace.policy import container_export_policy
from .params import RunCommandArgs, RunShellArgs
from .TerminalToolExecutionOutput import RunCommandOutput, RunShellOutput
from .workspace import SandboxWorkspace, collect_files, make_archive, read_archive
from .exception import TerminalErrorCode, TerminalToolError


@dataclass(frozen=True)
class SandboxLimits:
    image: str = "python-agent-sandbox:1"
    timeout_seconds: int = 60
    memory_mb: int = 512
    cpus: float = 1.0
    pids: int = 64
    disk_mb: int = 256
    max_output_bytes: int = 65536

    def __post_init__(self):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./:@-]{0,255}", self.image):
            raise ValueError("sandbox.image无效")
        for name, lower, upper in (("timeout_seconds", 1, 300), ("memory_mb", 64, 8192),
            ("pids", 8, 256), ("disk_mb", 16, 512), ("max_output_bytes", 1024, 1048576)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
                raise ValueError(f"sandbox.{name}超出允许范围")
        if isinstance(self.cpus, bool) or not isinstance(self.cpus, (float, int)) or not math.isfinite(self.cpus) or not 0 < self.cpus <= 4:
            raise ValueError("sandbox.cpus必须在0到4之间")


class ContainerExecutor:
    """任务独占一个容器；多条命令共享临时依赖，结束时统一清理。"""

    def __init__(self, workspace: SandboxWorkspace, limits: SandboxLimits):
        self.workspace, self.limits = workspace, limits
        self.docker = shutil.which("docker")
        self._name = None
        self._started = False
        self._dirty = False
        self._unsafe = False
        self._lock = threading.Lock()

    @staticmethod
    def _hidden():
        return {"creationflags": subprocess.CREATE_NO_WINDOW} if __import__("os").name == "nt" else {}

    def check_available(self):
        """没有Docker、Linux服务或本地镜像就拒绝，绝不回退到宿主执行。"""
        if not self.docker:
            raise TerminalToolError(TerminalErrorCode.SANDBOX_UNAVAILABLE, "未找到Docker，云端命令执行未开放")
        for args, expected in ((["info", "--format", "{{.OSType}}"], "linux"),
                               (["image", "inspect", self.limits.image, "--format", "{{.Id}}"], None)):
            try:
                result = subprocess.run([self.docker, *args], capture_output=True, timeout=10,
                    shell=False, check=False, text=True, **self._hidden())
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise TerminalToolError(TerminalErrorCode.SANDBOX_UNAVAILABLE, "容器运行环境不可用") from exc
            if result.returncode != 0 or expected is not None and result.stdout.strip() != expected:
                raise TerminalToolError(TerminalErrorCode.SANDBOX_UNAVAILABLE, "需要可用的Linux容器服务及预先构建的镜像")

    def docker_argv(self, name):
        """资源和权限由服务端固定，模型看不到也不能修改。"""
        limits = self.limits
        return [self.docker, "create", "--pull=never", "--name", name, "--log-driver=none",
            "--read-only", "--network=none", "--ipc=none", "--cap-drop=ALL",
            "--cap-add=SETUID", "--cap-add=SETGID", "--cap-add=KILL",
            "--security-opt=no-new-privileges:true", "--user=0:0",
            "--memory", f"{limits.memory_mb}m", "--memory-swap", f"{limits.memory_mb}m",
            "--cpus", str(limits.cpus), "--pids-limit", str(limits.pids),
            "--ulimit", "nofile=256:256", "--ulimit", "core=0:0",
            "--tmpfs", f"/workspace:rw,nosuid,nodev,size={limits.disk_mb}m,mode=0777",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777",
            self.limits.image, "serve"]

    def _invoke(self, action, request, *, maximum, timeout, cancellable=False):
        if not self._started or not self._name:
            raise TerminalToolError(TerminalErrorCode.SANDBOX_FAILED, "任务容器尚未启动")
        command = [self.docker, "exec", "-i", self._name, "python3", "-I",
                   "/opt/agent/container_entrypoint.py", action]
        process = None
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        exceeded = threading.Event()
        threads = []
        started = time.monotonic()
        try:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, shell=False, **self._hidden())

            def read(label, pipe):
                try:
                    while True:
                        chunk = pipe.read(65536)
                        if not chunk:
                            break
                        limit = maximum if label == "stdout" else 65536
                        available = limit - len(buffers[label])
                        buffers[label].extend(chunk[:max(available, 0)])
                        if len(chunk) > available:
                            exceeded.set()
                            break
                finally:
                    pipe.close()

            def send():
                try:
                    process.stdin.write(request)
                    process.stdin.close()
                except (OSError, ValueError):
                    pass

            for label in buffers:
                threads.append(threading.Thread(target=read, args=(label, getattr(process, label)), daemon=True))
            threads.append(threading.Thread(target=send, daemon=True))
            for thread in threads:
                thread.start()
            cancel = current_tool_cancellation() if cancellable else None
            while process.poll() is None:
                if cancel is not None and cancel.is_set():
                    process.kill()
                    raise TerminalToolError(TerminalErrorCode.CANCELLED, "容器命令已取消")
                if exceeded.is_set():
                    process.kill()
                    raise TerminalToolError(TerminalErrorCode.OUTPUT_LIMIT, "容器返回超过大小限制")
                if time.monotonic() - started > timeout:
                    process.kill()
                    raise TerminalToolError(TerminalErrorCode.TIMEOUT, "容器协议响应超时")
                time.sleep(0.02)
            for thread in threads:
                thread.join(timeout=2)
            if exceeded.is_set() or any(thread.is_alive() for thread in threads):
                raise TerminalToolError(TerminalErrorCode.OUTPUT_LIMIT, "容器协议输出不完整或超限")
            if process.returncode != 0:
                raise TerminalToolError(TerminalErrorCode.SANDBOX_FAILED, "隔离运行失败，未接收不完整结果")
            return bytes(buffers["stdout"])
        except OSError as exc:
            raise TerminalToolError(TerminalErrorCode.SANDBOX_UNAVAILABLE, "无法调用隔离运行环境") from exc
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                for thread in threads:
                    thread.join(timeout=2)

    def _sync_in(self):
        files = collect_files(self.workspace.root, self.workspace.limits)
        request = json.dumps({"archive": base64.b64encode(make_archive(files)).decode("ascii"),
                              "limits": vars(self.workspace.limits),
                              "policy": container_export_policy()}).encode()
        raw = self._invoke("import", request, maximum=65536, timeout=20)
        if json.loads(raw).get("ok") is not True:
            raise TerminalToolError(TerminalErrorCode.SANDBOX_FAILED, "项目源码送入任务容器失败")

    def _sync_out(self):
        request = json.dumps({"limits": vars(self.workspace.limits),
                              "policy": container_export_policy()}).encode()
        maximum = self.workspace.limits.max_bytes * 2 + self.workspace.limits.max_files * 4096 + 65536
        raw = self._invoke("export", request, maximum=maximum, timeout=20)
        try:
            result = json.loads(raw)
            files = read_archive(base64.b64decode(result["archive"], validate=True), self.workspace.limits)
        except Exception as exc:
            raise TerminalToolError(TerminalErrorCode.SANDBOX_FAILED, "任务容器返回的项目文件无效") from exc
        self.workspace.apply(files)
        self._dirty = False

    def start(self):
        """在 AgentLoop 开始前创建一次容器并送入初始源码。"""
        with self._lock:
            self._start_locked()

    def _start_locked(self):
        if self._started:
            return
        if self._unsafe:
            raise TerminalToolError(TerminalErrorCode.CLEANUP_FAILED, "执行环境状态异常")
        self.check_available()
        name = "agent-task-" + uuid.uuid4().hex
        try:
            created = subprocess.run(self.docker_argv(name), capture_output=True, timeout=10,
                                     shell=False, check=False, **self._hidden())
            if created.returncode != 0:
                raise TerminalToolError(TerminalErrorCode.SANDBOX_UNAVAILABLE, "无法创建满足安全限制的任务容器")
            started = subprocess.run([self.docker, "start", name], capture_output=True,
                                     timeout=10, shell=False, check=False, **self._hidden())
            if started.returncode != 0:
                raise TerminalToolError(TerminalErrorCode.SANDBOX_UNAVAILABLE, "无法启动任务容器")
            self._name, self._started = name, True
            self._sync_in()
        except BaseException:
            if self._started:
                try:
                    self._remove()
                except Exception:
                    pass
            elif self.docker:
                subprocess.run([self.docker, "rm", "-f", name], capture_output=True,
                               timeout=10, check=False, shell=False, **self._hidden())
            raise

    def _remove(self):
        """只删除服务端生成的任务容器名，并确认Docker服务仍然可用。"""
        name = self._name
        if not name:
            return
        try:
            removed = subprocess.run([self.docker, "rm", "-f", name], capture_output=True,
                timeout=10, check=False, shell=False, **self._hidden())
            status = subprocess.run([self.docker, "inspect", name], capture_output=True,
                timeout=10, check=False, shell=False, **self._hidden())
            health = subprocess.run([self.docker, "info", "--format", "{{.OSType}}"],
                capture_output=True, timeout=10, check=False, shell=False, **self._hidden())
            stderr = status.stderr.decode(errors="ignore") if isinstance(status.stderr, bytes) else status.stderr
            if status.returncode == 0 or health.returncode != 0 or (removed.returncode != 0 and "No such" not in stderr):
                raise RuntimeError("cleanup not confirmed")
        except Exception as exc:
            self._unsafe = True
            raise TerminalToolError(TerminalErrorCode.CLEANUP_FAILED, "无法确认任务容器已清理，禁止写回文件") from exc
        finally:
            self._started = False

    def close(self):
        """任务结束时删除容器；清理不确定会阻止真实项目写回。"""
        with self._lock:
            if not self._started:
                return
            sync_error = None
            if self._dirty:
                try:
                    self._sync_out()
                except Exception as exc:
                    sync_error = exc
            self._remove()
            if sync_error is not None:
                raise sync_error

    def execute(self, argv):
        with self._lock:
            if self._unsafe:
                raise TerminalToolError(TerminalErrorCode.CLEANUP_FAILED, "任务容器状态异常，拒绝再次运行")
            if not self._started:
                self._start_locked()
            self._sync_in()
            request = json.dumps({"argv": argv, "timeout_seconds": self.limits.timeout_seconds,
                "max_output_bytes": self.limits.max_output_bytes,
                "limits": vars(self.workspace.limits)}).encode()
            self._dirty = True
            raw = self._invoke("run", request, maximum=self.limits.max_output_bytes + 65536,
                               timeout=self.limits.timeout_seconds + 15, cancellable=True)
            try:
                result = json.loads(raw)
                if result.get("failure") not in {None, "TIMEOUT", "OUTPUT_LIMIT"}:
                    raise ValueError("environment failed")
            except Exception as exc:
                raise TerminalToolError(TerminalErrorCode.SANDBOX_FAILED, "任务容器返回无效") from exc
            self._sync_out()
            if result.get("failure"):
                code = TerminalErrorCode.TIMEOUT if result["failure"] == "TIMEOUT" else TerminalErrorCode.OUTPUT_LIMIT
                raise TerminalToolError(code, "命令超时或输出超限；已保留通过检查的项目文件")
            return result

    def run_command(self, program, args=None):
        parameters = RunCommandArgs(program=program, args=args or [])
        result = self.execute([parameters.program, *parameters.args])
        return RunCommandOutput(program=program, args=parameters.args, **{
            key: result[key] for key in ("exit_code", "stdout", "stderr", "duration_ms")}, truncated=False)

    def run_shell(self, command):
        parameters = RunShellArgs(command=command)
        result = self.execute(["/bin/sh", "-c", parameters.command])
        return RunShellOutput(command=command, shell="sh", **{
            key: result[key] for key in ("exit_code", "stdout", "stderr", "duration_ms")}, truncated=False)
