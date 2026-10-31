"""云端项目的固定 Git 操作；不执行模型命令、不调用 hooks/filter、不远程推送。

先用现有安全文件入口读取允许的字节，再交 Git 记录。这里不用 git add，
因此项目里的 .gitattributes 无法让 Git 运行用户指定的过滤程序。
"""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from ..config import Settings
from .exception import WorkspaceError, WorkspaceErrorCode
from .policy import open_export_file


class ProjectVersions:
    """一个项目一次成功运行最多产生一个提交；没有变化就不创建空版本。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _command(self, root: Path, args: list[str], data: bytes = b"", *,
                 extra_env: dict | None = None, allow_failure: bool = False) -> bytes:
        """固定参数列表执行 Git；限制时间、输出，并在失败时终止和回收进程。"""
        executable = shutil.which("git")
        timeout = self.settings.workspace_git_timeout_seconds
        output_limit = self.settings.workspace_git_max_output_bytes
        if not executable or timeout <= 0 or output_limit <= 0:
            raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "Git 不可用或配置无效")
        env = {key: value for key, value in os.environ.items()
               if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG"}}
        env.update({
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull, "GIT_TERMINAL_PROMPT": "0",
            "GIT_LITERAL_PATHSPECS": "1", "GIT_ATTR_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Agent Service", "GIT_AUTHOR_EMAIL": "agent@localhost",
            "GIT_COMMITTER_NAME": "Agent Service", "GIT_COMMITTER_EMAIL": "agent@localhost",
            "GIT_DIR": str(root / ".git"), "GIT_WORK_TREE": str(root),
        })
        env.update(extra_env or {})
        command = [executable, "-c", f"core.hooksPath={os.devnull}",
                   "-c", f"core.attributesFile={os.devnull}", "-c", "core.fsmonitor=false",
                   "-c", "commit.gpgSign=false", "-c", "protocol.allow=never", *args]
        # 临时文件收输入/输出，避免 stdin 管道写满或 communicate 无限积攒输出。
        try:
            with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output:
                source.write(data)
                source.seek(0)
                process = subprocess.Popen(command, cwd=root, env=env, stdin=source,
                                           stdout=output, stderr=output,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                started = time.monotonic()
                try:
                    while process.poll() is None:
                        if (time.monotonic() - started > timeout
                                or os.fstat(output.fileno()).st_size > output_limit):
                            raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE,
                                                 "Git 操作超时或输出超过上限")
                        time.sleep(0.01)
                    if os.fstat(output.fileno()).st_size > output_limit:
                        raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "Git 输出超过上限")
                    output.seek(0)
                    result = output.read(output_limit + 1)
                    if process.returncode and not allow_failure:
                        raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "项目版本记录失败")
                    return result if process.returncode == 0 else b""
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
        except OSError as exc:
            raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "无法运行 Git") from exc

    def prepare(self, root: Path) -> None:
        """仅初始化本项目仓库；已有 .git 不得是文件或链接，不寻找上级仓库。"""
        metadata = root / ".git"
        if metadata.is_symlink() or (metadata.exists() and not metadata.is_dir()):
            raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "项目 Git 目录不合法")
        if metadata.exists():
            if getattr(metadata.lstat(), "st_file_attributes", 0) & 0x400:
                raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "项目 Git 目录不能是链接")
            if not (metadata / "HEAD").is_file() or not (metadata / "objects").is_dir():
                raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "已有 Git 目录不完整")
            return  # 不重复 init，不改用户已有的项目仓库配置。
        self._command(root, ["init", "--template=", "--initial-branch=main", str(root)])

    def save(self, root: Path, paths, run_id: str) -> bool:
        """从安全文件清单构造完整版本，包括删除；不修改工作区，不重跑 Agent。"""
        self.prepare(root)
        file_limit = self.settings.workspace_git_max_file_bytes
        started = time.monotonic()
        if file_limit <= 0:
            raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "Git 文件上限配置无效")
        # 独立临时 index，不复用可能残留的暂存内容，失败不污染下一次版本。
        with tempfile.TemporaryDirectory(prefix="agent-git-") as temporary:
            env = {"GIT_INDEX_FILE": str(Path(temporary) / "index")}
            records = []
            total = 0
            for count, path in enumerate(paths, 1):
                if time.monotonic() - started > self.settings.workspace_git_timeout_seconds:
                    raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "版本准备超时")
                if count > self.settings.workspace_max_archive_files:
                    raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "版本文件数超过上限")
                stream, info = open_export_file(root, path)
                try:
                    if info.st_size > file_limit:
                        raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "版本文件过大")
                    content = stream.read(file_limit + 1)
                finally:
                    stream.close()
                total += len(content)
                if len(content) > file_limit or total > self.settings.workspace_max_archive_input_bytes:
                    raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "版本内容超过上限")
                oid = self._command(root, ["hash-object", "-w", "--no-filters", "--stdin"], content).strip()
                if not re.fullmatch(rb"[0-9a-f]{40,64}", oid):
                    raise WorkspaceError(WorkspaceErrorCode.GIT_UNAVAILABLE, "Git 对象返回异常")
                mode = b"100755" if info.st_mode & 0o111 else b"100644"
                records.append(mode + b" " + oid + b"\t" + path.encode("utf-8") + b"\0")
            self._command(root, ["read-tree", "--empty"], extra_env=env)
            self._command(root, ["update-index", "-z", "--index-info"], b"".join(records), extra_env=env)
            tree = self._command(root, ["write-tree"], extra_env=env).strip()
            previous = self._command(root, ["rev-parse", "--verify", "HEAD^{commit}"], allow_failure=True).strip()
            if previous:
                old_tree = self._command(root, ["rev-parse", "HEAD^{tree}"]).strip()
                if tree == old_tree:
                    return False
            elif not records:
                return False
            args = ["commit-tree", tree.decode("ascii"), "-m", f"Agent run {run_id}"]
            if previous:
                args += ["-p", previous.decode("ascii")]
            commit = self._command(root, args).strip().decode("ascii")
            self._command(root, ["update-ref", "HEAD", commit,
                                 previous.decode("ascii") if previous else "0" * 40])
            # 同步普通 index，方便维护者用 git status 查看；不改工作区文件。
            self._command(root, ["read-tree", tree.decode("ascii")])
            return True
