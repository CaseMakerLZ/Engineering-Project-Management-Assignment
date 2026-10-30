"""只保存当前已经生成的可见内容，不负责发送、读库或执行任务。"""

from dataclasses import dataclass, field
from typing import Any

from ..runs.models import RunStatus


@dataclass
class VisibleRun:
    """仅保存准许对外展示的内容，不持有 prompt、上下文、reasoning 或工具原文。"""

    status: RunStatus
    sequence: int = 0
    messages: dict[str, str] = field(default_factory=dict)
    text_bytes: int = 0
    result: str | None = None
    error: str | None = None
    finished_at: float | None = None
    stream_error: dict[str, Any] | None = None
    # 只保存当前正在执行的一个工具；顺序执行结束后清空，不累计完整调用历史。
    active_tool: dict[str, str] | None = None
