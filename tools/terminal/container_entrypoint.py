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
import shutil
import zipfile
import posixpath

# -I不包含脚本目录，只加入镜像内只读脚本路径，不加入用户项目目录。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dependency_policy import BUNDLE_BYTES, EXPANDED_BYTES, MAX_FILES, MAX_FILE_BYTES


ROOT = Path("/workspace")
MAX_INPUT = 64 * 1024 * 1024
SHARED_NODE_MODULES = Path("/opt/agent/node_modules")
DEPENDENCIES = Path('/deps')

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
    modules = DEPENDENCIES / 'npm/node_modules'
    chosen = modules if modules.is_dir() else SHARED_NODE_MODULES
    if not target.exists() and not target.is_symlink() and chosen.is_dir():
        target.symlink_to(chosen, target_is_directory=True)


def _dependency_target(name, root):
    """依赖归档独立于项目源码：允许.bin，但禁止绝对路径、穿越和链接父目录。"""
    parts = name.split('/')
    if (not name or name.startswith('/') or '\\' in name or ':' in name
            or any(p in {'', '.', '..'} for p in parts)
            or any(ord(c) < 32 for c in name)):
        raise ValueError('invalid dependency path')
    target = root.joinpath(*parts)
    if any(p.is_symlink() for p in target.parents if p != root.parent):
        raise ValueError('linked dependency parent')
    return target


def install_dependencies(request):
    """先在新目录验证并安装，全部成功才替换；失败继续使用旧环境。"""
    ecosystem = request.get('ecosystem')
    if ecosystem not in {'python', 'npm'}:
        raise ValueError('invalid dependency ecosystem')
    encoded = request.get('bundle')
    if not isinstance(encoded, str) or len(encoded) > BUNDLE_BYTES * 2:
        raise ValueError('bundle limit')
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) > BUNDLE_BYTES:
        raise ValueError('bundle limit')
    stage = DEPENDENCIES / 'pending'
    destination = DEPENDENCIES / ecosystem
    old = DEPENDENCIES / 'previous'
    # 这些路径只在root拥有的/deps内；用户命令不能改父目录。
    if stage.exists() or old.exists():
        raise ValueError('dependency staging not clean')
    stop_user_processes()
    stage.mkdir(mode=0o755)
    links, seen = [], set()
    total = 0
    try:
        with tarfile.open(fileobj=BytesIO(raw), mode='r:gz') as archive:
            for index, item in enumerate(archive):
                if index >= MAX_FILES or item.name in seen:
                    raise ValueError('dependency count or duplicate')
                seen.add(item.name)
                target = _dependency_target(item.name, stage)
                if not item.name.startswith('wheels/' if ecosystem == 'python' else 'node_modules/'):
                    raise ValueError('unexpected dependency content')
                target.parent.mkdir(parents=True, exist_ok=True)
                if item.issym() and ecosystem == 'npm':
                    link = item.linkname
                    normalized = posixpath.normpath(posixpath.join(posixpath.dirname(item.name), link))
                    if (not link or link.startswith('/') or '\\' in link or ':' in link
                            or not normalized.startswith('node_modules/')):
                        raise ValueError('dependency link escapes tree')
                    links.append((target, link))
                    continue
                total += item.size
                if not item.isfile() or item.size < 0 or item.size > MAX_FILE_BYTES or total > EXPANDED_BYTES:
                    raise ValueError('dependency size or type')
                stream = archive.extractfile(item)
                if stream is None:
                    raise ValueError('missing dependency')
                with stream, target.open('xb') as output:
                    shutil.copyfileobj(stream, output, length=65536)
                target.chmod(0o755 if item.mode & 0o111 else 0o644)
        for target, link in links:
            if target.exists() or target.is_symlink():
                raise ValueError('dependency link conflict')
            target.symlink_to(link)
            if not target.resolve().is_relative_to(stage.resolve()) or not target.exists():
                raise ValueError('invalid dependency link')
        if ecosystem == 'python':
            wheels = sorted((stage / 'wheels').iterdir())
            if not wheels or any(not f.is_file() or f.suffix != '.whl' for f in wheels):
                raise ValueError('only wheel dependencies supported')
            expanded = 0
            entries = 0
            for wheel in wheels:
                with zipfile.ZipFile(wheel) as z:
                    for item in z.infolist():
                        entries += 1
                        expanded += item.file_size
                        if entries > MAX_FILES or expanded > EXPANDED_BYTES or item.file_size > MAX_FILE_BYTES:
                            raise ValueError('expanded wheel limit')
                        _dependency_target(item.filename.rstrip('/'), stage)
                        if stat.S_ISLNK(item.external_attr >> 16):
                            raise ValueError('wheel link denied')
            installed = stage / 'site'
            installed.mkdir()
            os.chown(installed, 1000, 1000)
            def unprivileged():
                os.setgroups([])
                os.setgid(1000)
                os.setuid(1000)
            # 不加载项目、旧安装环境或网络配置。wheel安装不运行setup.py。
            completed = subprocess.run(['/opt/agent/venv/bin/python', '-I', '-m', 'pip',
                'install', '--no-index', '--no-deps', '--no-compile', '--no-cache-dir',
                '--target', str(installed), *map(str, wheels)],
                env={'PATH': '/usr/bin:/bin', 'HOME': '/tmp', 'TMPDIR': '/tmp',
                     'PIP_CONFIG_FILE': '/dev/null', 'PIP_DISABLE_PIP_VERSION_CHECK': '1'},
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=45, preexec_fn=unprivileged)
            if completed.returncode:
                raise ValueError('offline wheel install failed')
            shutil.rmtree(stage / 'wheels')
        if ecosystem == 'npm':
            # 预装包作为后备：未申请同名新版本的包继续可用，不复制大型目录。
            modules = stage / 'node_modules'
            modules.mkdir(exist_ok=True)
            for source in SHARED_NODE_MODULES.iterdir():
                target = modules / source.name
                if source.name == '.bin' or source.name.startswith('@'):
                    target.mkdir(exist_ok=True)
                    for child in source.iterdir():
                        leaf = target / child.name
                        if not leaf.exists() and not leaf.is_symlink():
                            leaf.symlink_to(child)
                elif not target.exists() and not target.is_symlink():
                    target.symlink_to(source, target_is_directory=source.is_dir())
        # 库在非root命令中导入；只读冻结，不允许替换已校验依赖目录。
        for directory, folders, files in os.walk(stage, followlinks=False):
            os.chown(directory, 0, 0)
            Path(directory).chmod(0o755)
            for name in files:
                path = Path(directory) / name
                if not path.is_symlink():
                    os.chown(path, 0, 0)
                    path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
        node_link = ROOT / 'node_modules'
        if ecosystem == 'npm' and (node_link.exists() or node_link.is_symlink()):
            if not node_link.is_symlink():
                raise ValueError('project node_modules changed; refusing overwrite')
            if str(node_link.readlink()) not in {str(SHARED_NODE_MODULES), str(destination / 'node_modules')}:
                raise ValueError('unexpected node_modules link')
        if destination.exists():
            destination.rename(old)
        try:
            stage.rename(destination)
            if ecosystem == 'npm':
                if node_link.is_symlink():
                    node_link.unlink()
                _ensure_shared_node_modules()
        except BaseException:
            if destination.exists():
                shutil.rmtree(destination)
            if old.exists():
                old.rename(destination)
            raise
        if old.exists():
            shutil.rmtree(old)
        return {'ok': True}
    finally:
        stop_user_processes()
        if stage.exists():
            shutil.rmtree(stage)


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
        "PATH": "/deps/python/site/bin:/deps/npm/node_modules/.bin:/opt/agent/venv/bin:/opt/agent/node_modules/.bin:/usr/local/bin:/usr/bin:/bin",
        "NODE_PATH": "/deps/npm/node_modules:/opt/agent/node_modules",
        "PYTHONPATH": "/deps/python/site",
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
                  "若工具列表有install_dependencies，可用包名和明确版本申请安装。\n"
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
    if action == 'dependencies':
        request = _read_request()
        try:
            result = install_dependencies(request)
        except Exception:
            # 普通安装拒绝保持协议完整，让调用方继续使用旧依赖；不泄露原错误。
            result = {'ok': False, 'error': 'DEPENDENCY_INSTALL_FAILED'}
            try:
                stop_user_processes()
            except Exception:
                result['cleanup_failed'] = True
        print(json.dumps(result))
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
