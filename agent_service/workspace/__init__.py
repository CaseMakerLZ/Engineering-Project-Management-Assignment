"""云端项目工作区：目录确认、公开导出策略、文件浏览与导出。

本包只负责"项目根目录内的受控文件访问"，不负责 HTTP 路由、Git 命令执行和
打包调度；那些分别由 http/routes.py、workspace/versions.py 和
workspace/service.py 承担。
"""

from .exception import WorkspaceError, WorkspaceErrorCode
from .models import DirectoryPage, FileEntry, FilePreview, WorkspaceStatus
from .policy import (
    build_project_root,
    is_exportable,
    is_exportable_dir,
    is_previewable,
    normalize_path,
    quote_project_path,
    resolve_in_project,
    resolve_project_directory,
)

__all__ = [
    "DirectoryPage",
    "FileEntry",
    "FilePreview",
    "WorkspaceError",
    "WorkspaceErrorCode",
    "WorkspaceStatus",
    "build_project_root",
    "is_exportable",
    "is_exportable_dir",
    "is_previewable",
    "normalize_path",
    "quote_project_path",
    "resolve_in_project",
    "resolve_project_directory",
]
