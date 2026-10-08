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
