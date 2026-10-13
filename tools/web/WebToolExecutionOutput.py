from pydantic import BaseModel


class SearchWebOutput(BaseModel):
    """搜索成功后的候选网页结果。"""

    query: str
    results: list[dict[str, str | None]]
    returned_count: int
    truncated: bool


class FetchURLOutput(BaseModel):
    """网页抓取和基础正文提取成功后的结果。"""

    requested_url: str
    final_url: str
    title: str | None
    content_type: str
    text: str
    links: list[dict[str, str]]
    media: list[dict[str, str]]
    truncated: bool
    extraction_status: str

