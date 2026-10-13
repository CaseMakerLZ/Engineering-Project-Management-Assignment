from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SearchWebArgs(BaseModel):
    """search_web 的模型可见参数；服务端凭据和网络限制不在这里。"""

    query: str = Field(min_length=1, max_length=512, description="自然语言搜索主题，不是 URL")
    max_results: int = Field(default=5, ge=1, le=10)
    time_range: Literal["any", "day", "week", "month"] = "any"

    @field_validator("query")
    @classmethod
    def check_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query 不能为空")
        return value


class FetchURLArgs(BaseModel):
    """fetch_url 的模型可见参数。请求限制由服务端配置。"""

    url: str = Field(min_length=1, max_length=2048, description="要读取的 HTTP 或 HTTPS URL")

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("url 不能为空")
        return value

