"""记忆工具的模型参数。

这里的参数只表达模型的回忆意图；项目、对话和当前运行时间由服务端绑定，
不会暴露给模型填写。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

    run_id: str | None = Field(
        default=None, min_length=1, max_length=64,
        description="指定运行ID；可读取服务端绑定的本轮内存过程；其他运行限当前项目、当前对话、本轮之前成功或失败运行",
    )
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
        description="历史时间范围；默认最近一周，指定 run_id 时默认不限历史起点，仍早于本轮",
    )
    limit: int = Field(default=5, ge=1, le=10, description="最多返回的历史运行数")
    include_process: bool = Field(
        default=False,
        description="是否附带 reasoning、工具调用和工具结果等运行过程",
    )
    process_offset: int = Field(
        default=0, ge=0,
        description="过程从末尾向前分段读取，每段最多100条；0为最近一段，继续时填写返回的process_next_offset并指定同一run_id",
    )
    process_sequence: int | None = Field(
        default=None, ge=0, description="只读指定序号的一条过程；与run_id、include_process=true配合，便于读取长工具结果",
    )
    content_offset: int = Field(
        default=0, ge=0, description="指定一条过程后，从其可读内容的此字符位置继续读取，每次最多4000字符",
    )

    @model_validator(mode="after")
    def validate_match_text(self) -> "SearchMemoryArgs":
        if self.run_id is not None:
            self.run_id = self.run_id.strip()
            if not self.run_id:
                raise ValueError("run_id 不能为空白")
        if self.process_offset and (not self.include_process or self.run_id is None):
            raise ValueError("分段读取过程时必须指定 run_id 并设置 include_process=true")
        if self.process_sequence is not None and (not self.include_process or self.run_id is None or self.process_offset):
            raise ValueError("指定过程序号时必须指定run_id、开启过程读取且process_offset为0")
        if self.content_offset and self.process_sequence is None:
            raise ValueError("内容翻页必须指定process_sequence")
        if self.match_text is not None:
            self.match_text = self.match_text.strip() or None
        return self


class RememberArgs(BaseModel):
    """remember 的显式长期记忆写入参数。"""

    model_config = ConfigDict(extra="forbid")

    memory_id: str | None = Field(
        default=None, min_length=1, max_length=64,
        description="更新已有记忆时填写；新建记忆留空",
    )
    content: str = Field(
        min_length=1, max_length=2_000,
        description="需要长期保留的明确事实、偏好、决定、目标或约束",
    )

    @model_validator(mode="after")
    def normalize_content(self) -> "RememberArgs":
        self.content = self.content.strip()
        if not self.content:
            raise ValueError("content 不能为空")
        if self.memory_id is not None:
            self.memory_id = self.memory_id.strip()
            if not self.memory_id:
                raise ValueError("memory_id 不能为空白；新建时请省略或传 null")
        return self
