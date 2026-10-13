"""终端程序正常结束时返回的业务结果；非零退出码也属于正常结果。"""

from pydantic import BaseModel


class RunCommandOutput(BaseModel):
    program: str
    args: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool


class RunShellOutput(BaseModel):
    command: str
    shell: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool
