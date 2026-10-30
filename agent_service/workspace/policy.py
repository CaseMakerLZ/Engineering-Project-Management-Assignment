"""项目工作区的路径校验与公开导出策略（唯一真源）。

目录树、文本预览、单文件下载、项目 ZIP 和 Git 提交都必须调用这里的判断，
避免五处各写一套排除规则后互相漂移（ZIP 打得出来、预览拒绝、Git 又提交了）。

本模块只做纯判断与受控打开，不负责分页、打包、Git 命令或 HTTP 状态码。

两条必须守住的设计边界：

* 只接受项目内 ``/`` 分隔的相对路径，拒绝绝对路径、盘符、UNC、``..``、反斜杠、
  NUL 和控制字符；越界检查逐层进行，不靠一次 ``resolve()`` 后比字符串前缀。
* 不把所有以点开头的名字一律排除。``.git`` 目录必须排除，但 ``.gitignore``、
  ``.github/`` 是正常项目文件，误删会让用户项目不可下载。
"""

from __future__ import annotations

import errno
import os
import re
import stat
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

from .exception import WorkspaceError, WorkspaceErrorCode

MAX_PATH_LENGTH = 4096
MAX_COMPONENT_LENGTH = 255

_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")

# 依赖、缓存、构建产物和版本库元数据：不进目录树、不预览、不下载、不打包、不提交。
_EXCLUDED_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn",
    ".aws", ".ssh", ".gnupg",
    "node_modules", "bower_components",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    ".venv", "venv", ".eggs",
    "target", "dist", "build", "out", ".next", ".nuxt", ".gradle",
    ".idea", ".vscode", ".cache", ".terraform", ".pnpm-store",
})

# 凭据、私钥和本地数据库文件：即使扩展名普通也不导出。
_EXCLUDED_FILE_NAMES = frozenset({
    ".npmrc", ".yarnrc", ".pypirc", ".netrc", ".git-credentials",
    ".dockercfg", ".pgpass", ".htpasswd",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
})

# .env 系列整体不导出，但提交进仓库的模板文件是正常项目文件。
_ENV_TEMPLATE_NAMES = frozenset({".env.example", ".env.sample", ".env.template"})

_EXCLUDED_SUFFIXES = frozenset({
    "pem", "key", "p12", "pfx", "jks", "keystore", "kdbx", "ppk",
    "sqlite", "sqlite3", "db", "db-journal", "mdb",
})

# 可预览的文本扩展名；不含 pdf/zip/图片等二进制格式。
_TEXT_SUFFIXES = frozenset({
    "txt", "md", "markdown", "rst", "adoc", "log",
    "py", "pyi", "ipynb",
    "java", "kt", "kts", "groovy", "scala", "clj",
    "js", "jsx", "mjs", "cjs", "ts", "tsx", "vue", "svelte",
    "json", "jsonc", "json5", "yaml", "yml", "toml", "ini", "cfg", "conf",
    "properties", "xml", "plist", "csv", "tsv",
    "html", "htm", "xhtml", "css", "scss", "sass", "less", "svg",
    "sh", "bash", "zsh", "fish", "ps1", "psm1", "bat", "cmd",
    "c", "h", "cc", "cpp", "cxx", "hpp", "hxx", "cs", "go", "rs",
    "rb", "php", "pl", "pm", "lua", "swift", "dart", "r",
    "sql", "graphql", "gql", "proto", "thrift",
    "gradle", "mk", "cmake", "diff", "patch",
})

# 没有扩展名但在项目里有明确文本语义的文件。
_TEXT_FILE_NAMES = frozenset({
    "makefile", "dockerfile", "containerfile", "jenkinsfile", "procfile",
    "gemfile", "rakefile", "vagrantfile", "brewfile", "justfile", "taskfile",
    "license", "licence", "notice", "readme", "changelog", "authors",
    "contributing", "codeowners", "requirements",
    ".gitignore", ".gitattributes", ".dockerignore", ".npmignore",
    ".editorconfig", ".prettierrc", ".eslintrc", ".babelrc",
    ".nvmrc", ".python-version", ".tool-versions",
})


# 项目号与用户号都只允许可移植的单层目录名。
# 不加这条限制时，一个带斜杠或盘符的 ID 就能把目录拼到别处去。
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}")


def is_valid_identifier(value: str | None) -> bool:
    """判断是否是安全的单层目录名（项目号、用户号共用同一规则）。"""

    return isinstance(value, str) and bool(_IDENTIFIER_PATTERN.fullmatch(value))


def build_project_relative(user_id: str | None, project_id: str | None) -> str:
    """返回项目在受控工作区根下的相对路径（布局的唯一字符串定义处）。

    ``user_id`` 与 ``project_id`` 都必须来自可信来源（数据库记录、服务端配置），
    不能来自模型参数或浏览器请求体。
    """

    if not is_valid_identifier(user_id):
        raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "用户标识不合法")
    if not is_valid_identifier(project_id):
        raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "项目标识不合法")
    return f"users/{user_id}/projects/{project_id}"


def build_project_root(
    workspace_root: str | Path, user_id: str | None, project_id: str | None
) -> Path:
    """按 ``workspace_root/users/{user_id}/projects/{project_id}`` 拼出项目根目录。

    这是多租户路径隔离的定义处：租户（用户）→ 资源（项目）→ 内容（文件）。
    只做拼接，不创建目录、不检查链接；要拿到可以真正使用的目录，请用
    :func:`resolve_project_directory`。
    """

    return Path(workspace_root).expanduser() / build_project_relative(user_id, project_id)


def resolve_project_directory(
    workspace_root: str | Path, user_id: str | None, project_id: str | None
) -> Path:
    """拼出项目根目录并逐层做链接与越界检查，返回受控路径（不保证已存在）。

    与 :func:`build_project_root` 的区别是它真的会检查每一层：任何一层是符号
    链接、或者结果跑出了工作区根，都直接拒绝。目录是否已经准备好由调用方另行
    判断（准备接口负责创建，运行阶段不应悄悄替用户创建目录）。
    """

    root = Path(workspace_root).expanduser()
    return resolve_in_project(root, build_project_relative(user_id, project_id))


def _lstat_or_none(path: Path) -> os.stat_result | None:
    """取 ``lstat``，不存在返回 None，其它 IO 错误统一转成工作区不可用。"""

    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise WorkspaceError(WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "无法检查项目路径") from exc


def ensure_project_directory(
    workspace_root: str | Path, user_id: str | None, project_id: str | None
) -> Path:
    """逐层创建项目目录并返回它；只补缺失目录，不删除、不清空任何内容。

    不用 ``mkdir(parents=True)``：递归创建会一次性穿过中间层，中间某一层如果
    在检查之后被换成符号链接，目录就会建到工作区外面。这里一层一层地
    "先 lstat、缺了就 mkdir、建完再 lstat"，每层都拒绝链接和非目录。

    重复调用是幂等(幂等：同一个操作执行一次和多次效果一样，重复执行不产生副作用)的：已存在的目录保持原样，已有文件和 ``.git`` 都不会被触碰
    （本函数根本不进入项目目录内部）。
    """

    root = Path(workspace_root).expanduser()
    if not root.is_dir():
        raise WorkspaceError(WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "工作区根目录不存在")

    current = root
    for part in build_project_relative(user_id, project_id).split("/"):
        current = current / part
        info = _lstat_or_none(current)
        if info is None:
            try:
                os.mkdir(current)
            except FileExistsError:
                # 并发创建或刚被别人建好，下面统一按实际类型再审一次。
                pass
            except OSError as exc:
                raise WorkspaceError(
                    WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "无法创建项目工作区"
                ) from exc
            info = _lstat_or_none(current)
            if info is None:
                raise WorkspaceError(
                    WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "项目工作区创建后不可见"
                )
        if stat.S_ISLNK(info.st_mode):
            raise WorkspaceError(WorkspaceErrorCode.PATH_FORBIDDEN, "不接受符号链接")
        if not stat.S_ISDIR(info.st_mode):
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "项目工作区路径被非目录占用"
            )
    return current


def normalize_path(raw: str | None) -> str:
    """把外部传入的项目内相对路径规范化成 ``""``（根）或 ``"a/b/c"``。

    只做校验和拼接，不做静默修补：``a//b``、``a/``、``./a``、``a/../b`` 全部
    视为非法，而不是"帮用户改成正确形式"。这样越界尝试会稳定报错，不会因为
    一次宽容的规范化而落到另一个位置。
    """

    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "路径必须是字符串")
    if raw == "":
        return ""
    if len(raw) > MAX_PATH_LENGTH:
        raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "路径过长")
    try:
        raw.encode("utf-8")
    except UnicodeEncodeError as exc:
        # 孤立代理项等无法编码到 UTF-8 的字符串不能进入文件系统。
        raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "路径包含非法字符") from exc
    if "\\" in raw:
        raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "路径必须使用 / 分隔")
    if raw.startswith("/"):
        raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "不接受绝对路径")
    if _DRIVE_PATTERN.match(raw):
        raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "不接受盘符路径")
    for character in raw:
        if character == "\x00" or ord(character) < 0x20 or ord(character) == 0x7F:
            raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "路径包含控制字符")

    parts = raw.split("/")
    for part in parts:
        if part in {"", ".", ".."}:
            raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "路径包含非法片段")
        if len(part) > MAX_COMPONENT_LENGTH:
            raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "路径片段过长")
    return "/".join(parts)


def _is_excluded_dir(name: str) -> bool:
    """判断目录名是否属于排除名单（依赖、缓存、构建产物、版本库元数据）。"""

    return name.lower() in _EXCLUDED_DIR_NAMES


def _is_excluded_file(name: str) -> bool:
    """判断文件名是否属于排除名单（凭据、私钥、本地数据库）。

    ``.env`` 系列整体拒绝，但提交进仓库的模板（``.env.example`` 等）放行。
    """

    lower = name.lower()
    if lower in _ENV_TEMPLATE_NAMES:
        return False
    if lower in _EXCLUDED_FILE_NAMES:
        return True
    if lower.startswith(".env"):
        return True
    _, dot, suffix = lower.rpartition(".")
    return bool(dot) and suffix in _EXCLUDED_SUFFIXES


def is_exportable(relative_path: str | None) -> bool:
    """判断一个项目内文件是否允许对外导出（预览/下载/ZIP/Git 共用）。

    非法路径也返回 ``False`` 而不是抛异常：目录枚举会逐个名字调用本函数，
    一个名字古怪的普通条目不应该让整页目录读取失败。真正的用户输入路径要先用
    :func:`normalize_path` 校验，那里会给出明确的 INVALID_PATH。

    判定规则：任一层组件命中排除目录（``.git``、``node_modules`` 等）即拒绝，
    最后一段再按凭据/数据库/私钥规则判断。目录条目请用
    :func:`is_exportable_dir`，本函数对"名字恰好是 build 的普通文件"也会拒绝，
    属于有意的保守取舍。
    """

    try:
        path = normalize_path(relative_path)
    except WorkspaceError:
        return False
    if not path:
        return False
    parts = path.split("/")
    if any(_is_excluded_dir(part) for part in parts):
        return False
    return not _is_excluded_file(parts[-1])


def is_exportable_dir(relative_path: str | None) -> bool:
    """判断一个项目内目录条目是否允许出现在目录树里。

    目录只需要通过排除目录名单；项目根 ``""`` 本身不作为子项返回。
    """

    try:
        path = normalize_path(relative_path)
    except WorkspaceError:
        return False
    if not path:
        return False
    return not any(_is_excluded_dir(part) for part in path.split("/"))


def is_previewable(relative_path: str) -> bool:
    """判断文件是否可以按 UTF-8 文本预览。

    先要求可导出，再看扩展名或已知无扩展名文件名；不判断实际编码，编码在读取
    时按严格 UTF-8 解码确认为准。
    """

    try:
        path = normalize_path(relative_path)
    except WorkspaceError:
        return False
    if not path or not is_exportable(path):
        return False
    name = path.rsplit("/", 1)[-1].lower()
    if name in _TEXT_FILE_NAMES:
        return True
    _, dot, suffix = name.rpartition(".")
    return bool(dot) and suffix in _TEXT_SUFFIXES


def resolve_in_project(project_root: str | Path, relative_path: str | None) -> Path:
    """把项目内相对路径解析成受控绝对路径，路径不存在也返回预期位置。

    逐层用 ``lstat`` 检查，任何一层是符号链接都拒绝，避免"检查后再被替换"的
    常见越界手法；最后再做一次"必须仍在项目根内"的深度防御。不追随链接意味着
    本函数不会因为链接而读到项目外的内容。
    """

    root = Path(project_root).expanduser()
    if not root.is_dir():
        raise WorkspaceError(WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "项目工作区不可用")
    path = normalize_path(relative_path)
    if not path:
        return root

    current = root
    for part in path.split("/"):
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            # 该层不存在，后面的层自然也不存在；继续拼接得到完整预期路径。
            continue
        except OSError as exc:
            raise WorkspaceError(
                WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "无法检查项目路径"
            ) from exc
        if stat.S_ISLNK(info.st_mode):
            raise WorkspaceError(WorkspaceErrorCode.PATH_FORBIDDEN, "不接受符号链接")

    try:
        resolved = current.resolve(strict=False)
    except OSError as exc:
        raise WorkspaceError(WorkspaceErrorCode.PATH_FORBIDDEN, "路径无法解析") from exc
    root_resolved = root.resolve()
    if resolved != root_resolved and not resolved.is_relative_to(root_resolved):
        raise WorkspaceError(WorkspaceErrorCode.PATH_FORBIDDEN, "路径超出项目范围")
    return current


def entry_kind(mode: int) -> str | None:
    """把 ``st_mode`` 映射成对外类型；设备、FIFO、socket 等一律不导出。"""

    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    return None


def stat_entry(project_root: str | Path, relative_path: str | None) -> os.stat_result:
    """取一个项目内条目的 ``lstat`` 结果，不追随链接。"""

    path = resolve_in_project(project_root, relative_path)
    try:
        return os.lstat(path)
    except FileNotFoundError as exc:
        raise WorkspaceError(WorkspaceErrorCode.ENTRY_NOT_FOUND, "目标不存在") from exc
    except OSError as exc:
        raise WorkspaceError(
            WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "无法读取目标信息"
        ) from exc


def _is_unfollowable_link_error(exc: OSError) -> bool:
    """``O_NOFOLLOW`` 命中链接、权限不足、是目录时统一按"禁止导出"处理。"""

    candidates = {
        getattr(errno, "ELOOP", -1),
        getattr(errno, "EMLINK", -1),
        errno.EACCES,
        errno.EPERM,
        errno.EISDIR,
        errno.ENOTDIR,
    }
    return exc.errno in candidates


def open_export_file(
    project_root: str | Path, relative_path: str, *, allow_hardlink: bool = False
) -> tuple[BinaryIO, os.stat_result]:
    """安全打开一个允许导出的文件，返回文件对象和打开瞬间的 ``fstat``。

    调用方应基于返回的 ``fstat`` 判断大小，并始终读这个句柄；不要再用路径重新
    打开一次，否则中间被替换就会"检查的是 A、发出去的是 B"。

    Linux 上使用 ``O_NOFOLLOW`` 打开，命中链接直接失败。``st_nlink > 1`` 的普通
    文件默认拒绝：硬链接可能把项目内路径指向项目外的敏感文件，这是本周的保守
    处置，允许通过参数显式放开。
    """

    path = resolve_in_project(project_root, relative_path)
    if not is_exportable(relative_path):
        raise WorkspaceError(WorkspaceErrorCode.PATH_FORBIDDEN, "目标文件不允许导出")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(os.fspath(path), flags)
    except FileNotFoundError as exc:
        raise WorkspaceError(WorkspaceErrorCode.ENTRY_NOT_FOUND, "目标不存在") from exc
    except OSError as exc:
        if _is_unfollowable_link_error(exc):
            raise WorkspaceError(WorkspaceErrorCode.PATH_FORBIDDEN, "目标文件不允许导出") from exc
        raise WorkspaceError(
            WorkspaceErrorCode.WORKSPACE_UNAVAILABLE, "无法打开目标文件"
        ) from exc

    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise WorkspaceError(WorkspaceErrorCode.PATH_FORBIDDEN, "目标不是普通文件")
        if info.st_nlink > 1 and not allow_hardlink:
            raise WorkspaceError(WorkspaceErrorCode.PATH_FORBIDDEN, "目标文件存在可疑链接")
    except BaseException:
        os.close(descriptor)
        raise
    return os.fdopen(descriptor, "rb"), info


def quote_project_path(relative_path: str) -> str:
    """URL 编码项目内相对路径，保留 ``/`` 作为目录分隔。

    用于把文件路径拼进 Java 下载接口的查询参数（``?path=src/main.py``）。
    """

    return quote(normalize_path(relative_path), safe="/")
