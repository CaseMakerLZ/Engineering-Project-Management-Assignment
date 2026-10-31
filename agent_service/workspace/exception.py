"""工作区域内的领域异常与错误码。

Java 按 ``code`` 翻译成 HTTP 状态码，不解析异常文本，也不把未知异常原文送到
页面。具体失败原因由错误码表达，不为每种场景创建独立异常类。

``message`` 必须是可以直接写进日志和内部响应的安全文案：不包含服务器真实
路径、不包含原始 OSError 文本、不包含令牌。
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class WorkspaceErrorCode(str, Enum):
    """云端项目工作区的内部错误码。

    编码与 Java 的 ErrorCode 分开维护：这里表达 Python 侧真实失败原因，Java
    再按第 6.5 节表格翻译成 400/404/409/413/415/503。
    """

    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    ENTRY_NOT_FOUND = "ENTRY_NOT_FOUND"
    INVALID_PATH = "INVALID_PATH"
    PATH_FORBIDDEN = "PATH_FORBIDDEN"
    PROJECT_BUSY = "PROJECT_BUSY"
    CURSOR_EXPIRED = "CURSOR_EXPIRED"
    DOWNLOAD_LIMIT = "DOWNLOAD_LIMIT"
    DIRECTORY_TOO_LARGE = "DIRECTORY_TOO_LARGE"
    PREVIEW_TOO_LARGE = "PREVIEW_TOO_LARGE"
    PREVIEW_UNSUPPORTED = "PREVIEW_UNSUPPORTED"
    DOWNLOAD_TOO_LARGE = "DOWNLOAD_TOO_LARGE"
    ARCHIVE_TOO_LARGE = "ARCHIVE_TOO_LARGE"
    PROJECT_QUOTA_EXCEEDED = "PROJECT_QUOTA_EXCEEDED"
    WORKSPACE_UNAVAILABLE = "WORKSPACE_UNAVAILABLE"
    GIT_UNAVAILABLE = "GIT_UNAVAILABLE"


class WorkspaceError(ValueError):
    """工作区域业务异常，等价于 Java 端的 ``BaseException``。

    继承 ``ValueError`` 与 ``tools/exceptions.py`` 的 ``ToolError`` 保持一致，
    便于现有执行器层把未知 ValueError 归为参数错误；新代码应通过 ``code``
    判断语义，而不是匹配异常文本。
    """

    def __init__(
        self,
        code: str | Enum,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        """保存错误码与安全文案，``cause`` 只用于服务端排查、不对外返回。"""

        super().__init__(message)
        self.code = code.value if isinstance(code, Enum) else str(code)
        self.message = message
        # details 只放可公开的补充信息，例如限制值、相对路径；不放绝对路径。
        self.details = details or {}
        self.cause = cause

    @property
    def error_code(self) -> str:
        """Java 风格的别名，便于服务层统一读取。"""

        return self.code

    def public_message(self) -> str:
        """返回可交给 Java 与页面的安全文案。"""

        return self.message
