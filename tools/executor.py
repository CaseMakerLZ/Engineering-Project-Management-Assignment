import json
import asyncio
from contextvars import ContextVar
import threading
from dataclasses import dataclass

from typing import Any
from pydantic import BaseModel, ValidationError
from tools.registry import ToolRegistry
from tools.exceptions import ToolError, ToolErrorCode


# asyncio.to_thread 会复制当前上下文；终端工具可读取本次执行独有的取消信号。
_current_cancellation: ContextVar[threading.Event | None] = ContextVar(
    "tool_cancellation", default=None
)


def current_tool_cancellation() -> threading.Event | None:
    return _current_cancellation.get()

@dataclass
class ToolExecutionResult:
    '''
    此设计表示情况:
    (假设使用calculator计算4+6)
    ToolExecutionResult(
        success=True,
        output=10
    )
    (假设除以0)
    ToolExecutionResult(
        success=False,
        output="不能除以0"
    )
    '''
    success: bool
    output: Any = None
    error: str | None = None
    # 机器可判断的错误语义；error 继续保留给 Agent 的可读提示。
    error_code: str | None = None

class ToolExecutor:
    def __init__(self,registry: ToolRegistry):
        self.registry = registry

    @staticmethod
    def _failure(exc: BaseException) -> ToolExecutionResult:
        """把不同来源的异常统一转换为稳定的工具失败结果。"""
        if isinstance(exc, ToolError):
            return ToolExecutionResult(
                success=False,
                error=exc.public_message(),
                error_code=exc.error_code,
            )
        if isinstance(exc, KeyError):
            return ToolExecutionResult(
                success=False,
                error="工具不存在",
                error_code=ToolErrorCode.NOT_FOUND.value,
            )
        if isinstance(exc, (json.JSONDecodeError, ValidationError, TypeError)):
            return ToolExecutionResult(
                success=False,
                error="工具参数无效",
                error_code=ToolErrorCode.INVALID_ARGUMENT.value,
            )
        if isinstance(exc, ValueError):
            # 兼容尚未迁移到领域异常的旧工具实现。
            return ToolExecutionResult(
                success=False,
                error=str(exc),
                error_code=ToolErrorCode.INVALID_ARGUMENT.value,
            )
        # 未预期异常不把底层堆栈或凭据泄露给模型。
        return ToolExecutionResult(
            success=False,
            error="工具执行失败",
            error_code=ToolErrorCode.INTERNAL_ERROR.value,
        )

    # 这里统一捕获异常；工具领域异常在进入这里前已经携带错误码。
    # 注意：本方法是同步函数。在 async 环境（AgentLoop）中必须通过
    def execute(self,tool_name: str,arguments: str) -> ToolExecutionResult:
        try:
            # 单独处理注册表查询，避免把工具实现内部的 KeyError 误判成“工具不存在”。
            try:
                tool = self.registry.get(tool_name)
            except KeyError:
                return ToolExecutionResult(
                    success=False,
                    error="工具不存在",
                    error_code=ToolErrorCode.NOT_FOUND.value,
                )
            #先初步将传入的json字符串转化为参数字典
            raw_args: dict[str,Any] = json.loads(arguments)
            #校验参数字典(实际上左边是一个解析后的对象，若解析成功就成功构建对象，否则会抛异常，无法执行下去)
            #假如抛异常，我暂时不处理它，之后再构建完整的异常体系
            validated_args = tool.args_model.model_validate(raw_args)
            #将得到的对象先通过model.dump化为字典格式，再用**解包成参数列表
            result = tool.function(**validated_args.model_dump())
            #具体工具可以返回自己的 Output 模型；执行外壳统一保存 JSON 兼容数据。
            if isinstance(result, BaseModel):
                result = result.model_dump(mode="json")
            return ToolExecutionResult(
                success=True,
                output=result
            )
        except Exception as exc:
            return self._failure(exc)

    async def execute_async(self, tool_name: str, arguments: str) -> ToolExecutionResult:
        """将同步工具放入线程，避免终端进程阻塞异步 AgentLoop。"""

        cancellation = threading.Event()
        token = _current_cancellation.set(cancellation)
        try:
            worker = asyncio.create_task(asyncio.to_thread(self.execute, tool_name, arguments))
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                cancellation.set()
                # 等待工作线程结束，确保终端工具已清理其进程树。
                await asyncio.shield(worker)
                raise
        finally:
            _current_cancellation.reset(token)

