"""网络工具共享的异常和错误码。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from tools.exceptions import ToolError


class WebErrorCode(str, Enum):
    INVALID_ARGUMENT = "WEB_INVALID_ARGUMENT"
    CONFIGURATION_ERROR = "WEB_CONFIGURATION_ERROR"
    URL_NOT_ALLOWED = "WEB_URL_NOT_ALLOWED"
    NETWORK_ERROR = "WEB_NETWORK_ERROR"
    DEPENDENCY_UNAVAILABLE = "WEB_DEPENDENCY_UNAVAILABLE"
    AUTHENTICATION_FAILED = "WEB_AUTHENTICATION_FAILED"
    RATE_LIMITED = "WEB_RATE_LIMITED"
    REMOTE_ERROR = "WEB_REMOTE_ERROR"
    RESPONSE_FORMAT_ERROR = "WEB_RESPONSE_FORMAT_ERROR"
    REDIRECT_ERROR = "WEB_REDIRECT_ERROR"
    RESOURCE_NOT_FOUND = "WEB_RESOURCE_NOT_FOUND"
    ACCESS_DENIED = "WEB_ACCESS_DENIED"
    CONTENT_UNSUPPORTED = "WEB_CONTENT_UNSUPPORTED"
    RESOURCE_LIMIT = "WEB_RESOURCE_LIMIT"
    EXTRACTION_ERROR = "WEB_EXTRACTION_ERROR"


class WebToolError(ToolError):
    """网络工具领域异常；具体场景由 ``WebErrorCode`` 区分。"""

    def __init__(
        self,
        code: WebErrorCode | str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(code, message, details=details, cause=cause)
