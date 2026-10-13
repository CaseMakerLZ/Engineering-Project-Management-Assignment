"""文件工具共享的异常和错误码。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from tools.exceptions import ToolError


class FilesystemErrorCode(str, Enum):
    INVALID_ARGUMENT = "FILESYSTEM_INVALID_ARGUMENT"
    CONFIGURATION_ERROR = "FILESYSTEM_CONFIGURATION_ERROR"
    PATH_BOUNDARY = "FILESYSTEM_PATH_BOUNDARY"
    PROTECTED_PATH = "FILESYSTEM_PROTECTED_PATH"
    NOT_FOUND = "FILESYSTEM_NOT_FOUND"
    WRONG_TARGET_TYPE = "FILESYSTEM_WRONG_TARGET_TYPE"
    RESOURCE_LIMIT = "FILESYSTEM_RESOURCE_LIMIT"
    CONTENT_UNSUPPORTED = "FILESYSTEM_CONTENT_UNSUPPORTED"
    VERSION_CONFLICT = "FILESYSTEM_VERSION_CONFLICT"
    WRITE_CONFLICT = "FILESYSTEM_WRITE_CONFLICT"
    IO_ERROR = "FILESYSTEM_IO_ERROR"


class FilesystemToolError(ToolError):
    """文件工具领域异常；具体场景由 ``FilesystemErrorCode`` 区分。"""

    def __init__(
        self,
        code: FilesystemErrorCode | str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(code, message, details=details, cause=cause)
