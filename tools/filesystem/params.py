from pathlib import Path

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

#工具工作需要具体的工作目录，所以先留下一个workspace字段，理论上项目要可以跨平台适配（即Linux(线上部署环境)和Windows(用户不登录，本地运行环境)上都要可以正常运行，但是两个OS在文件系统上就有很大不同）
#实际项目的情况下，project_id一定要对应相应文件夹（本地文件夹/云服务器上的文件夹）
workspace: str = ""

class ListDirectoryArgs(BaseModel):
    directory: Path = Path(".")         #位置（相对于工作区）
    max_depth: int = Field(default=1, ge=1, le=3, description="递归最大深度")
    max_entries: int = Field(default=150, ge=1, le=1000)  #默认最多返回150个文件或者目录
    patterns: list[str] | None = None #用于匹配相关名称文件，可以传递多个pattern用于匹配

    @classmethod
    @field_validator("directory")
    def check_directory(cls,v):
        if not str(v).strip():
            raise ValueError(f"{v} :目录不存在!")
        return v

class ReadTextFileArgs(BaseModel):
    file: Path
    start_line: int = Field(default=1,ge=1)
    max_lines: int = Field(default=200,ge=1,le=500)
    encoding: str = Field(default="utf-8",description="文本编码")
    #truncated: bool = Field(description="表示是否被截断")
    #文件大小还是不要给agent决定，直接交给java端控制
    #max_bytes: int = Field(gt=0,le=2 * 1024 * 1024,description="表示传入的文本文件大小(1B~2MB)")
    @classmethod
    @field_validator("file")
    def check_file_available(cls, v):
        # 模型给的是项目内相对路径；实际文件应由 service 在 workspace_root 下检查。
        if not str(v).strip():
            raise ValueError("file 不能为空")
        return v


class SearchTextArgs(BaseModel):
    query: str = Field(min_length=1, max_length=256, description="要查找的普通文本，不是正则表达式")
    directory: Path = Path(".")
    patterns: list[str] | None = None
    case_sensitive: bool = False
    max_results: int = Field(default=100, ge=1, le=500)

    @field_validator("query")
    @classmethod
    def check_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query 不能为空")
        return value


class WriteTextFileArgs(BaseModel):
    file: Path
    content: str
    overwrite: bool = False
    create_parents: bool = True
    expected_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")


class InsertBeforeChange(BaseModel):
    operation: Literal["insert_before"]
    anchor: str = Field(min_length=1)
    content: str


class InsertAfterChange(BaseModel):
    operation: Literal["insert_after"]
    anchor: str = Field(min_length=1)
    content: str


class ReplaceChange(BaseModel):
    operation: Literal["replace"]
    old_text: str = Field(min_length=1)
    new_text: str


class DeleteChange(BaseModel):
    operation: Literal["delete"]
    old_text: str = Field(min_length=1)


class AppendChange(BaseModel):
    operation: Literal["append"]
    content: str


EditChange = Annotated[
    InsertBeforeChange
    | InsertAfterChange
    | ReplaceChange
    | DeleteChange
    | AppendChange,
    Field(discriminator="operation"),
]


class EditTextFileArgs(BaseModel):
    file: Path
    # 编辑必须基于最近一次读取到的文件版本，避免覆盖其他人的修改。
    expected_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    changes: list[EditChange] = Field(min_length=1, max_length=50)
