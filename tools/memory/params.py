"""记忆工具的模型参数。

这里的参数只表达模型的回忆意图；项目、对话和当前运行时间由服务端绑定，
不会暴露给模型填写。
"""

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MemoryTimeRange(BaseModel):
    """可选的历史运行时间范围；不填写时由 service 使用最近一周。"""

    start: datetime | None = Field(default=None, description="时间范围起点（含）")
    end: datetime | None = Field(default=None, description="时间范围终点（不含）")

    @model_validator(mode="after")
    def validate_order(self) -> "MemoryTimeRange":
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("time_range.start 不能晚于 time_range.end")
        return self


class SearchMemoryArgs(BaseModel):
    """search_memory 的模型可填写参数。"""

    match_text: str | None = Field(
        default=None,
        max_length=256,
        description="回忆线索；只有 fuzzy_match=true 时才进行文本筛选",
    )
    fuzzy_match: bool = Field(
        default=False,
        description="是否启用受控文本匹配；默认关闭，不代表语义相似度检索",
    )
    time_range: MemoryTimeRange = Field(
        default_factory=MemoryTimeRange,
        description="历史时间范围；未指定边界时默认查询最近一周",
    )
    limit: int = Field(default=5, ge=1, le=10, description="最多返回的历史运行数")
    include_process: bool = Field(
        default=False,
        description="是否附带 reasoning、工具调用和工具结果等运行过程",
    )

    @model_validator(mode="after")
    def validate_match_text(self) -> "SearchMemoryArgs":
        if self.match_text is not None:
            self.match_text = self.match_text.strip() or None
        return self


class RememberArgs(BaseModel):
    """remember 的显式长期记忆写入参数。"""

    operation: Literal["UPSERT"] = Field(
        default="UPSERT", description="当前版本只支持新增或更新长期记忆"
    )
    memory_id: str | None = Field(
        default=None, min_length=1, max_length=64,
        description="更新已有记忆时填写；新建记忆留空",
    )
    memory_type: Literal[
        "FACT", "PREFERENCE", "DECISION", "GOAL", "CONSTRAINT", "PROCEDURE", "PROGRESS"
    ] = Field(description="记忆的业务类型")
    content: str = Field(
        min_length=1, max_length=2_000,
        description="需要长期保留的明确事实、偏好、决定、目标或约束",
    )
    supersedes_memory_id: str | None = Field(
        default=None, min_length=1, max_length=64,
        description="本条记忆替代的旧记忆 ID；不替代时留空",
    )

    @model_validator(mode="after")
    def normalize_content(self) -> "RememberArgs":
        self.content = self.content.strip()
        if not self.content:
            raise ValueError("content 不能为空")
        if self.memory_id is not None:
            self.memory_id = self.memory_id.strip() or None
        if self.supersedes_memory_id is not None:
            self.supersedes_memory_id = self.supersedes_memory_id.strip() or None
        if self.memory_id is not None and self.memory_id == self.supersedes_memory_id:
            raise ValueError("memory_id 不能替代自己")
        return self
