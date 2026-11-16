"""任务依赖协调：下载容器无项目，代理无宿主端口，结果仅送入断网任务。"""
import base64
import json
import secrets
import subprocess
import threading
import time
import uuid

from .dependency_policy import validate_packages, MAX_INSTALLS, DOWNLOAD_SECONDS, BUNDLE_BYTES
from .exception import TerminalErrorCode, TerminalToolError

# 一个服务进程最多准备一批依赖，不随任务数无限增加下载器。
_DOWNLOAD_SLOT = threading.BoundedSemaphore(1)


def _failure(code, message):
    return TerminalToolError(code, message)


def _run(executor, args, *, timeout=15, input=None, maximum=65536):
    """限制Docker协议输出；超时与取消时结束CLI，外层负责删除准确容器。"""
    from tools.executor import current_tool_cancellation
    process = subprocess.Popen([executor.docker, *args], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, **executor._hidden())
    output, errors = bytearray(), bytearray()
    exceeded = threading.Event()

    def read(pipe, target, limit):
        try:
            while True:
                data = pipe.read(32768)
                if not data:
                    break
                available = max(0, limit - len(target))
                target.extend(data[:available])
                if len(data) > available:
                    exceeded.set()
                    break
        finally:
            pipe.close()

    def send():
        try:
            process.stdin.write(input or b'')
            process.stdin.close()
        except OSError:
            pass

    threads = [threading.Thread(target=read, args=(process.stdout, output, maximum), daemon=True),
               threading.Thread(target=read, args=(process.stderr, errors, 65536), daemon=True),
               threading.Thread(target=send, daemon=True)]
    for thread in threads:
        thread.start()
    started = time.monotonic()
    cancel = current_tool_cancellation()
    try:
        while process.poll() is None:
            if exceeded.is_set():
                raise _failure(TerminalErrorCode.RESOURCE_LIMIT, '依赖协议输出超限')
            if cancel is not None and cancel.is_set():
                raise _failure(TerminalErrorCode.CANCELLED, '依赖准备已取消')
            if time.monotonic() - started > timeout:
                raise _failure(TerminalErrorCode.DEPENDENCY_FAILED, '依赖准备超时')
            time.sleep(.05)
        for thread in threads:
            thread.join(timeout=2)
        if exceeded.is_set() or any(t.is_alive() for t in threads) or process.returncode:
            raise _failure(TerminalErrorCode.DEPENDENCY_FAILED,
                '依赖操作失败：请检查版本、仓库网络、安装格式或资源限制；未开放任意网络')
        return bytes(output)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=2)


def download_bundle(executor, ecosystem, packages):
    """只给代理外网；下载器只接内部网络，没有项目/宿主挂载和公开端口。"""
    prefix = 'agent-deps-' + uuid.uuid4().hex
    network, proxy, installer = prefix + '-net', prefix + '-proxy', prefix + '-installer'
    token = secrets.token_urlsafe(32)
    cleanup_errors = []
    try:
        _run(executor, ['network', 'create', '--internal', network])
        common = ['--pull=never', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges:true', '--pids-limit', '48', '--cpus', '.5',
            '--memory-swap', '256m', '--memory', '256m', '--log-driver=none',
            '--ulimit', 'nofile=128:128', '--ulimit', 'core=0:0', '--user=1000:1000']
        # 代理由固定脚本执行；无包内容、用户代码或项目数据，外网只连接固定仓库。
        _run(executor, ['create', '--name', proxy, *common,
            '--network', 'bridge', '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=8m',
            '-e', f'AGENT_DOWNLOAD_TOKEN={token}', '--entrypoint', 'python3',
            executor.limits.image, '-I', '/opt/agent/dependency_proxy.py'])
        _run(executor, ['network', 'connect', '--alias', 'repository', network, proxy])
        _run(executor, ['start', proxy])
        _run(executor, ['exec', proxy, 'python3', '-c',
            "import socket,time; "
            "exec(\"for _ in range(30):\\n try:\\n  s=socket.create_connection(('127.0.0.1',18081),.2); s.close(); break\\n except OSError: time.sleep(.1)\\nelse: raise RuntimeError('proxy not ready')\")"])
        # 不读项目package.json/.npmrc/requirements.txt。仅服务端校验后的显式申请。
        url = f'http://agent:{token}@repository:18081'
        _run(executor, ['create', '-i', '--name', installer, *common,
            '--network', network, '--tmpfs', '/workspace:rw,nosuid,nodev,size=160m,mode=0777',
            '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777',
            '-e', f'HTTPS_PROXY={url}', '-e', f'HTTP_PROXY={url}',
            '-e', f'https_proxy={url}', '-e', f'http_proxy={url}',
            '--entrypoint', 'python3', executor.limits.image,
            '-I', '/opt/agent/dependency_installer.py'])
        # 固定脚本先导入模块，再连接代理，已给代理足够启动时间；不自动重试安装。
        payload = _run(executor, ['start', '-a', '-i', installer], timeout=DOWNLOAD_SECONDS + 15,
            input=json.dumps({'ecosystem': ecosystem, 'packages': packages}).encode(),
            maximum=BUNDLE_BYTES * 2 + 65536)
        data = json.loads(payload)
        bundle = base64.b64decode(data['bundle'], validate=True)
        if len(bundle) > BUNDLE_BYTES or data.get('packages') != packages:
            raise ValueError('invalid dependency bundle')
        return data['bundle']
    finally:
        # 即使create响应丢失，也只按服务端随机名称精确清理，不枚举用户容器。
        for name in (installer, proxy):
            try:
                result = subprocess.run([executor.docker, 'rm', '-f', name], capture_output=True,
                    timeout=15, **executor._hidden())
                inspected = subprocess.run([executor.docker, 'inspect', name], capture_output=True,
                    timeout=10, **executor._hidden())
                if inspected.returncode == 0 or (result.returncode and b'No such' not in result.stderr):
                    cleanup_errors.append(name)
            except Exception:
                cleanup_errors.append(name)
        try:
            # create响应超时也可能已成功创建，因此无条件按精确名字检查并清理。
            removed = subprocess.run([executor.docker, 'network', 'rm', network], capture_output=True,
                timeout=15, **executor._hidden())
            if removed.returncode and b'not found' not in removed.stderr and b'No such' not in removed.stderr:
                cleanup_errors.append(network)
        except Exception:
            cleanup_errors.append(network)
        try:
            health = subprocess.run([executor.docker, 'info', '--format', '{{.OSType}}'],
                capture_output=True, timeout=10, **executor._hidden())
            if health.returncode or health.stdout.strip() != b'linux':
                cleanup_errors.append('docker')
        except Exception:
            cleanup_errors.append('docker')
        if cleanup_errors:
            executor._unsafe = True
            raise _failure(TerminalErrorCode.CLEANUP_FAILED, '无法确认下载环境已清理，停止任务写回')


def install_dependencies(executor, ecosystem, packages):
    """在容器锁内完成完整替换；失败不改变之前可用依赖，不在宿主安装。"""
    packages = validate_packages(ecosystem, packages)
    with executor._lock:
        if not executor.dependencies_enabled:
            raise _failure(TerminalErrorCode.DENIED, '管理员尚未开启按需依赖安装')
        if executor._unsafe or not executor._started:
            raise _failure(TerminalErrorCode.SANDBOX_UNAVAILABLE, '任务环境尚不可用')
        if executor._dependency_attempts >= MAX_INSTALLS:
            raise _failure(TerminalErrorCode.RESOURCE_LIMIT, '本任务最多申请四次依赖安装')
        merged = {p['name']: p['version'] for p in executor._dependency_packages.get(ecosystem, [])}
        merged.update({p['name']: p['version'] for p in packages})
        complete = validate_packages(ecosystem, [{'name': k, 'version': v} for k, v in sorted(merged.items())])
        if not _DOWNLOAD_SLOT.acquire(blocking=False):
            raise _failure(TerminalErrorCode.RESOURCE_LIMIT, '依赖下载名额已满，请稍后重试')
        executor._dependency_attempts += 1
        try:
            encoded = download_bundle(executor, ecosystem, complete)
            try:
                raw = executor._invoke('dependencies', json.dumps({'ecosystem': ecosystem,
                    'bundle': encoded}).encode(), maximum=65536, timeout=60, cancellable=True)
            except BaseException:
                # CLI中断不证明容器内安装已停止；必须销毁任务，不接受并发写回。
                executor._unsafe = True
                raise
            result = json.loads(raw)
            if result.get('cleanup_failed'):
                executor._unsafe = True
                raise _failure(TerminalErrorCode.CLEANUP_FAILED, '依赖安装进程清理不确定，禁止写回')
            if result.get('ok') is not True:
                raise ValueError('dependency installation failed')
            executor._dependency_packages[ecosystem] = complete
            return {'ecosystem': ecosystem, 'packages': complete, 'installed': True,
                'scope': '仅本任务；源码清单未修改，普通命令仍断网，任务结束删除依赖',
                'note': '如需后续复现，请另行更新项目requirements.txt或package.json；不自动编辑它们'}
        except TerminalToolError:
            raise
        except Exception as exc:
            raise _failure(TerminalErrorCode.DEPENDENCY_FAILED,
                '依赖准备失败，之前成功安装的环境仍保留；请检查包版本、体积与格式') from exc
        finally:
            _DOWNLOAD_SLOT.release()
