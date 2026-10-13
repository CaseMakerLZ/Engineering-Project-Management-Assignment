from pydantic import BaseModel, Field


class ListDirectoryOutput(BaseModel):
    """list_directory 的业务结果；执行成功与否由 ToolExecutionResult 表示。"""

    path: str
    entries: list[dict[str, str]]
    returned_count: int
    truncated: bool

class ReadFileOutput(BaseModel):
    """
    service.py下read_text_file函数的执行结果，执行成功与否由 ToolExecutionResult 表示。
    """
    path: str
    start_line: int
    end_line: int #注意！我这里用的是结束行号而不是max_lines，主要是文件可能没那么多行
    raw: str = Field(exclude=True) #纯文件内容，供直接调用 service 的程序使用；序列化时不发给 LLM
    content: str #文件内容，行首带行号（便于LLM在有需要的时候更准确的指出相应行号，比如说修改文件时，它肯定要提前读取，此时就可以准确指出行号）
    truncated: bool
    sha256: str  # 原文件字节的哈希值，可用于修改前检查版本


class SearchTextOutput(BaseModel):
    """普通文本搜索的匹配位置和扫描是否完整。"""

    query: str
    matches: list[dict[str, str | int | bool]]
    returned_count: int
    truncated: bool
    skipped_files: int


class WriteFileOutput(BaseModel):
    """完整写入后的文件信息，不重复返回提交的正文。"""

    path: str
    created: bool
    overwritten: bool
    bytes_written: int
    sha256: str


class EditFileOutput(BaseModel):
    """一组局部编辑成功后的文件信息。"""

    path: str
    applied_changes: int
    bytes_written: int
    sha256: str
