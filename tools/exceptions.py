"""工具系统的公共异常定义。

工具实现只需要抛出 ``ToolError``（或某个工具大类的子类），执行器就可以
统一把失败转换为 ``ToolExecutionResult``。具体失败原因通过错误码表达，
而不是为每一种失败场景再创建一个异常类。
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ToolErrorCode(str, Enum):
    """跨工具通用的错误码。

    工具大类可以在自己的 ``exception.py`` 中定义更细的错误码；这里保留
    执行器必须理解的通用码。
    """

    INVALID_ARGUMENT = "TOOL_INVALID_ARGUMENT"
    NOT_FOUND = "TOOL_NOT_FOUND"
    CONFIGURATION_ERROR = "TOOL_CONFIGURATION_ERROR"
    INTERNAL_ERROR = "TOOL_INTERNAL_ERROR"


class ToolError(ValueError):
    """工具层业务异常，等价于 Java 端的 ``BaseException``。

    继承 ``ValueError`` 是为了兼容当前直接调用工具的测试和调用方；新的
    代码应当通过 ``code`` 判断错误语义，而不要依赖 Python 异常文本。
    """

    def __init__(
        self,
        code: str | Enum,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code.value if isinstance(code, Enum) else str(code)
        self.message = message
        self.details = details or {}
        self.cause = cause

    @property
    def error_code(self) -> str:
        """Java 风格的别名，便于服务层统一读取。"""

        return self.code

    def public_message(self) -> str:
        """返回可交给 Agent 的安全错误文本。"""

        return self.message
