"""只在无项目、无凭据的下载容器中运行；不接收Shell或用户清单文件。"""
import base64
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import subprocess
import tarfile
import time
from urllib.parse import urlsplit
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dependency_policy import (validate_packages, BUNDLE_BYTES, EXPANDED_BYTES,
    MAX_FILES, MAX_FILE_BYTES, DOWNLOAD_SECONDS)


def validate_lock(lock):
    """npm全依赖只能来自官方仓库；拒绝Git、文件和任意URL依赖。"""
    packages = lock.get('packages')
    if not isinstance(packages, dict) or len(packages) > 1500:
        raise ValueError('dependency graph limit')
    for path, package in packages.items():
        if not path:
            continue
        if not isinstance(package, dict) or package.get('link'):
            raise ValueError('linked dependency denied')
        url = urlsplit(package.get('resolved', ''))
        if url.scheme != 'https' or url.hostname != 'registry.npmjs.org' or url.port not in (None, 443) or url.username or url.password:
            raise ValueError('nonregistry dependency denied')
        for key in ('dependencies', 'optionalDependencies', 'peerDependencies'):
            for value in package.get(key, {}).values():
                if not isinstance(value, str) or any(c in value for c in ('/', ':', '\\')):
                    raise ValueError('external dependency specifier denied')


def bundle(root):
    """流式限制解包体积和条数，npm仅接受树内相对符号链接。"""
    output = BytesIO()
    total = count = 0
    with tarfile.open(fileobj=output, mode='w:gz', compresslevel=2) as archive:
        for directory, folders, files in os.walk(root, followlinks=False):
            for name in list(folders) + files:
                path = Path(directory) / name
                info = path.lstat()
                if stat.S_ISDIR(info.st_mode):
                    continue
                relative = path.relative_to(root).as_posix()
                count += 1
                total += info.st_size
                if count > MAX_FILES or total > EXPANDED_BYTES or info.st_size > MAX_FILE_BYTES:
                    raise ValueError('installed dependencies exceed limit')
                item = tarfile.TarInfo(relative)
                if stat.S_ISLNK(info.st_mode):
                    target = os.readlink(path)
                    if target.startswith('/') or not path.resolve().is_relative_to(root.resolve()):
                        raise ValueError('external dependency link denied')
                    item.type, item.linkname = tarfile.SYMTYPE, target
                    archive.addfile(item)
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    item.size, item.mode = info.st_size, info.st_mode & 0o777
                    with path.open('rb') as stream:
                        archive.addfile(item, stream)
                else:
                    raise ValueError('special dependency file denied')
                if output.tell() > BUNDLE_BYTES:
                    raise ValueError('dependency bundle limit')
    if len(output.getvalue()) > BUNDLE_BYTES:
        raise ValueError('dependency bundle limit')
    return output.getvalue()


def main():
    started = time.monotonic()
    request = json.loads(__import__('sys').stdin.buffer.read(4097))
    ecosystem = request['ecosystem']
    packages = validate_packages(ecosystem, request['packages'])
    root = Path('/workspace/payload')
    root.mkdir()
    env = {k: v for k, v in os.environ.items() if k in {
        'PATH', 'HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'}}
    env.update(HOME='/tmp', TMPDIR='/tmp', LANG='C.UTF-8',
        PIP_INDEX_URL='https://pypi.org/simple', PIP_EXTRA_INDEX_URL='',
        PIP_CONFIG_FILE='/dev/null', PIP_DISABLE_PIP_VERSION_CHECK='1',
        npm_config_cache='/workspace/cache', npm_config_registry='https://registry.npmjs.org',
        npm_config_ignore_scripts='true', npm_config_audit='false', npm_config_fund='false',
        npm_config_userconfig='/tmp/npmrc-user', npm_config_globalconfig='/tmp/npmrc-global',
        GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_ALLOW_PROTOCOL='')

    def command(argv):
        remaining = DOWNLOAD_SECONDS - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError()
        with Path('/workspace/install.log').open('wb') as logfile:
            result = subprocess.run(argv, cwd=root, env=env, stdin=subprocess.DEVNULL,
                stdout=logfile, stderr=subprocess.STDOUT, timeout=remaining, check=False)
        if result.returncode:
            raise ValueError('package resolution or download failed')

    if ecosystem == 'python':
        wheels = root / 'wheels'
        wheels.mkdir()
        command(['/opt/agent/venv/bin/python', '-m', 'pip', 'download', '--only-binary=:all:',
            '--index-url', 'https://pypi.org/simple', '--no-input', '--retries', '0',
            '--timeout', '15', '--no-cache-dir', '--dest', str(wheels),
            *[f"{p['name']}=={p['version']}" for p in packages]])
        if not all(p.suffix == '.whl' for p in wheels.iterdir()):
            raise ValueError('only wheels supported')
    else:
        (root / 'package.json').write_text(json.dumps({'name': 'agent-task-dependencies',
            'version': '1.0.0', 'private': True,
            'dependencies': {p['name']: p['version'] for p in packages}}))
        command(['npm', 'install', '--package-lock-only', '--ignore-scripts', '--no-audit', '--no-fund'])
        validate_lock(json.loads((root / 'package-lock.json').read_text()))
        command(['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund', '--omit=dev'])
        # 临时清单仅用于解析，不会覆盖用户项目的package.json或锁文件。
        (root / 'package.json').unlink()
        (root / 'package-lock.json').unlink()
    payload = bundle(root)
    print(json.dumps({'bundle': base64.b64encode(payload).decode('ascii'), 'packages': packages}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # 包名/版本可见，但不返回可能含代理口令的原始错误。
        print(json.dumps({'error': 'DEPENDENCY_DOWNLOAD_FAILED'}))
        raise SystemExit(1)
