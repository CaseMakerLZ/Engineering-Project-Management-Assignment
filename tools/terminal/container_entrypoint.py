"""镜像内受信任的命令监督程序。

容器在一个 Agent 任务期间常驻；源码通过受限归档同步，命令始终降权为
1000:1000 执行。依赖目录留在容器内，任务结束后随容器一起删除。
"""

import base64
from io import BytesIO
import json
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import sys
import tarfile
import time


ROOT = Path("/workspace")
MAX_INPUT = 64 * 1024 * 1024
SHARED_NODE_MODULES = Path("/opt/agent/node_modules")

def _read_request():
    raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise ValueError("input protocol limit")
    return json.loads(raw)


def _policy_values(policy, key):
    values = policy.get(key)
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise ValueError("invalid export policy")
    return frozenset(value.lower() for value in values)


def _excluded_file(name, policy):
    lower = name.lower()
    templates = _policy_values(policy, "environment_templates")
    if lower in templates:
        return False
    if lower in _policy_values(policy, "files") or lower.startswith(".env"):
        return True
    _, dot, suffix = lower.rpartition(".")
    return bool(dot) and suffix in _policy_values(policy, "suffixes")


def _excluded_dir(name, policy):
    lower = name.lower()
    return (lower in _policy_values(policy, "directories")
            or _excluded_file(name, policy)
            or lower in _policy_values(policy, "environment_templates"))


def _valid_name(name, policy):
    parts = name.split("/")
    return (name and not name.startswith("/") and "\\" not in name and ":" not in name
            and all(part not in {"", ".", ".."} for part in parts)
            and all(not _excluded_dir(part, policy) for part in parts[:-1])
            and not _excluded_file(parts[-1], policy)
            and parts[-1].lower() not in _policy_values(policy, "directories"))


def _clear_managed(policy, directory=ROOT):
    """清除上一次同步的源码，保留本任务的依赖、缓存和构建结果。"""
    with os.scandir(directory) as entries:
        for entry in entries:
            if _excluded_dir(entry.name, policy):
                continue
            path = Path(directory) / entry.name
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                _clear_managed(policy, path)
                path.rmdir()
            else:
                path.unlink()


def _ensure_shared_node_modules():
    target = ROOT / "node_modules"
    if not target.exists() and not target.is_symlink() and SHARED_NODE_MODULES.is_dir():
        target.symlink_to(SHARED_NODE_MODULES, target_is_directory=True)


def unpack(raw, policy, max_files, max_bytes, max_file_bytes):
    """替换受管理源码；不进入依赖目录，也不使用 tarfile.extract。"""
    _clear_managed(policy)
    total, names = 0, set()
    with tarfile.open(fileobj=BytesIO(raw), mode="r:") as archive:
        for item in archive:
            if (not item.isfile() or not _valid_name(item.name, policy) or item.name.casefold() in names
                    or item.size < 0 or item.size > max_file_bytes):
                raise ValueError("invalid input archive")
            names.add(item.name.casefold())
            total += item.size
            if len(names) > max_files or total > max_bytes:
                raise ValueError("input limit")
            target = ROOT / item.name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o777)
            for parent in target.parents:
                if parent == ROOT:
                    break
                if parent.is_symlink():
                    raise ValueError("input parent link")
                parent.chmod(0o777)
            source = archive.extractfile(item)
            if source is None:
                raise ValueError("incomplete input archive")
            with source, target.open("xb") as output:
                payload = source.read(item.size + 1)
                if len(payload) != item.size:
                    raise ValueError("incomplete input archive")
                output.write(payload)
            target.chmod(0o666)
    _ensure_shared_node_modules()


def pack(policy, max_files, max_bytes, max_file_bytes):
    """只导出项目源码；临时依赖、缓存、凭据和构建目录不计入归档。"""
    output, total, count, scanned = BytesIO(), 0, 0, 0
    with tarfile.open(fileobj=output, mode="w") as archive:
        for directory, folders, files in os.walk(ROOT, followlinks=False):
            folders[:] = [name for name in folders if not _excluded_dir(name, policy)]
            for name in files:
                if (_excluded_file(name, policy)
                        or name.lower() in _policy_values(policy, "directories")):
                    continue
                scanned += 1
                if scanned > max_files * 4:
                    raise ValueError("output entries limit")
                path = Path(directory) / name
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError("output contains link or special file")
                relative = path.relative_to(ROOT).as_posix()
                if not _valid_name(relative, policy):
                    continue
                count += 1
                total += info.st_size
                if count > max_files or total > max_bytes or info.st_size > max_file_bytes:
                    raise ValueError("output limit")
                item = tarfile.TarInfo(relative)
                item.size, item.mode = info.st_size, 0o600
                with path.open("rb") as stream:
                    archive.addfile(item, stream)
    return output.getvalue()


def _user_processes():
    current = os.getpid()
    result = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal() or int(entry.name) in {1, current}:
            continue
        try:
            status = (entry / "status").read_text(encoding="utf-8")
            uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
            if int(uid_line.split()[1]) == 1000:
                result.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError, StopIteration, ValueError):
            continue
    return result


def stop_user_processes():
    """每条命令结束后清掉UID 1000的遗留进程，依赖文件仍保留。"""
    until = time.monotonic() + 2
    while time.monotonic() < until:
        processes = _user_processes()
        if not processes:
            return
        for pid in processes:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(0.02)
    raise RuntimeError("container child cleanup not confirmed")


def run_command(request):
    import resource
    command = request["argv"]
    limits = request["limits"]
    if not command or not all(isinstance(part, str) and "\x00" not in part for part in command):
        raise ValueError("invalid argv")

    def restrict():
        os.setgroups([])
        os.setgid(1000)
        os.setuid(1000)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limits["max_file_bytes"], limits["max_file_bytes"]))

    environment = {
        "PATH": "/opt/agent/venv/bin:/opt/agent/node_modules/.bin:/usr/local/bin:/usr/bin:/bin",
        "NODE_PATH": "/opt/agent/node_modules",
        "HOME": "/tmp", "TMPDIR": "/tmp", "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "npm_config_update_notifier": "false", "npm_config_audit": "false",
    }
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=restrict,
        start_new_session=True, env=environment)
    pipes = {process.stdout: bytearray(), process.stderr: bytearray()}
    active, failure, cleaned = list(pipes), None, False
    while active or process.poll() is None:
        if time.monotonic() - started > request["timeout_seconds"]:
            failure = "TIMEOUT"
            break
        ready, _, _ = select.select(active, [], [], 0.05)
        for stream in ready:
            chunk = os.read(stream.fileno(), 4096)
            if not chunk:
                active.remove(stream)
                continue
            if sum(len(value) for value in pipes.values()) + len(chunk) > request["max_output_bytes"]:
                failure = "OUTPUT_LIMIT"
                break
            pipes[stream].extend(chunk)
        if failure:
            break
        if process.poll() is not None and not cleaned:
            # 后台进程可能继续占着输出管道；主命令结束就清场，但保留文件。
            stop_user_processes()
            cleaned = True
    if failure and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        code = process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        code = process.wait(timeout=2)
    if not cleaned:
        stop_user_processes()
    stdout = pipes[process.stdout].decode("utf-8", errors="replace")
    stderr = pipes[process.stderr].decode("utf-8", errors="replace")
    missing = ("ModuleNotFoundError", "No module named", "ERR_MODULE_NOT_FOUND",
               "Cannot find module", "Cannot find package")
    if code != 0 and any(marker in stderr for marker in missing):
        stderr = ("当前任务环境缺少所需依赖。常用依赖已预装；其他依赖尚不能任意联网安装。\n"
                  + stderr)
    return {"exit_code": code, "stdout": stdout, "stderr": stderr,
            "duration_ms": int((time.monotonic() - started) * 1000), "failure": failure}


def serve():
    """作为容器PID1常驻；真实命令由受信任脚本的run模式执行。"""
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    def reap(_signum, _frame):
        try:
            while os.waitpid(-1, os.WNOHANG)[0] > 0:
                pass
        except ChildProcessError:
            pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGCHLD, reap)
    while not stopping:
        signal.pause()
    stop_user_processes()


def main():
    if sys.platform != "linux" or os.getuid() != 0 or not Path("/.dockerenv").is_file():
        raise SystemExit("This entrypoint requires its dedicated Linux container")
    action = sys.argv[1] if len(sys.argv) == 2 else ""
    if action == "serve":
        if os.getpid() != 1:
            raise ValueError("serve must be PID1")
        serve()
        return
    if action == "import":
        request = _read_request()
        unpack(base64.b64decode(request["archive"], validate=True), request["policy"],
               **request["limits"])
        print(json.dumps({"ok": True}))
        return
    if action == "export":
        request = _read_request()
        archive = pack(request["policy"], **request["limits"])
        print(json.dumps({"archive": base64.b64encode(archive).decode("ascii")}))
        return
    if action == "run":
        print(json.dumps(run_command(_read_request())))
        return
    raise ValueError("invalid action")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        print(json.dumps({"failure": "ENVIRONMENT_FAILED"}))
        raise SystemExit(125)
