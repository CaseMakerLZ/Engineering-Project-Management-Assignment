"""Agent 上下文组装模块。

这里放“本轮开始前如何准备上下文”和“运行中如何整理工作上下文”的代码。
不放记忆工具的执行逻辑。
记忆工具仍属于 tools 包，因为它们会被模型主动调用。
"""

from .builder import ContextBuilder, ContextSnapshot, DEFAULT_SYSTEM_PROMPT

__all__ = ["ContextBuilder", "ContextSnapshot", "DEFAULT_SYSTEM_PROMPT"]
