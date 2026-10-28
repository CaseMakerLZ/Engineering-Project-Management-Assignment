"""文字发送功能的限制异常；不为每个限制场景新增异常类。"""

class EventLimitError(RuntimeError):
    """明确报告运行内存、连接或可见输出超过上限，不偷偷裁掉内容。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
