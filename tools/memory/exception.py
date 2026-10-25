"""记忆工具领域异常和错误码。"""

from enum import Enum
from typing import Any

from tools.exceptions import ToolError


class MemoryErrorCode(str, Enum):
    INVALID_ARGUMENT = "MEMORY_INVALID_ARGUMENT"
    CONFIGURATION_ERROR = "MEMORY_CONFIGURATION_ERROR"
    RESOURCE_LIMIT = "MEMORY_RESOURCE_LIMIT"
    STORAGE_ERROR = "MEMORY_STORAGE_ERROR"


class MemoryToolError(ToolError):
    """记忆工具失败；具体原因通过错误码表达。"""

    def __init__(
        self,
        code: MemoryErrorCode | str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(code, message, details=details, cause=cause)
