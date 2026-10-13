from functools import partial

import httpx

from tools.registry import ToolDefinition

from .params import FetchURLArgs, SearchWebArgs
from .service import fetch_url, search_web


def build_web_tools(
    *,
    api_key: str | None,
    search_endpoint: str = "https://api.tavily.com/search",
    timeout_seconds: float = 10.0,
    max_response_bytes: int = 2 * 1024 * 1024,
    max_redirects: int = 3,
    http_client: httpx.Client | None = None,
) -> list[ToolDefinition]:
    """创建网络工具；凭据和请求限制由服务端绑定，不暴露给模型。"""
    return [
        ToolDefinition(
            name="search_web",
            description="根据自然语言主题搜索候选网页，返回标题、URL 和摘要。",
            args_model=SearchWebArgs,
            function=partial(
                search_web,
                api_key=api_key,
                endpoint=search_endpoint,
                timeout_seconds=timeout_seconds,
                http_client=http_client,
            ),
        ),
        ToolDefinition(
            name="fetch_url",
            description="读取指定的 HTTP 或 HTTPS 网页，提取标题、正文、链接和图片元数据。",
            args_model=FetchURLArgs,
            function=partial(
                fetch_url,
                timeout_seconds=timeout_seconds,
                max_response_bytes=max_response_bytes,
                max_redirects=max_redirects,
                http_client=http_client,
            ),
        ),
    ]

