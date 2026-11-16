"""模型可见的终端工具参数。工作目录和限制由服务端绑定。"""

from pydantic import BaseModel, Field, field_validator
from typing import Literal


MAX_ARGUMENTS = 64
MAX_ARGUMENT_LENGTH = 4096
MAX_ARGUMENTS_LENGTH = 16384
MAX_COMMAND_LENGTH = 16384


def _no_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("参数不能包含 NUL 字符")
    return value


class RunCommandArgs(BaseModel):
    program: str = Field(min_length=1, max_length=MAX_ARGUMENT_LENGTH)
    args: list[str] = Field(default_factory=list, max_length=MAX_ARGUMENTS)

    @field_validator("program")
    @classmethod
    def validate_program(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("program 不能为空")
        return _no_nul(value)

    @field_validator("args")
    @classmethod
    def validate_args(cls, value: list[str]) -> list[str]:
        if sum(len(item) for item in value) > MAX_ARGUMENTS_LENGTH:
            raise ValueError("参数总长度超过限制")
        for item in value:
            if len(item) > MAX_ARGUMENT_LENGTH:
                raise ValueError("单个参数超过长度限制")
            _no_nul(item)
        return value


class RunShellArgs(BaseModel):
    command: str = Field(min_length=1, max_length=MAX_COMMAND_LENGTH)

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("command 不能为空")
        return _no_nul(value)


class DependencyPackage(BaseModel):
    """只描述包和版本；不接受来源URL、命令或真实目录。"""
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=50)


class InstallDependenciesArgs(BaseModel):
    model_config = {"extra": "forbid"}
    ecosystem: Literal['python', 'npm']
    packages: list[DependencyPackage] = Field(min_length=1, max_length=8)

    @field_validator('packages')
    @classmethod
    def validate_package_strings(cls, value):
        for item in value:
            _no_nul(item.name)
            _no_nul(item.version)
        return value
