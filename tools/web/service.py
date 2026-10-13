from __future__ import annotations

from html.parser import HTMLParser
from ipaddress import ip_address
import json
from pathlib import PurePosixPath
import socket
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from tools.web.WebToolExecutionOutput import FetchURLOutput
from .WebToolExecutionOutput import FetchURLOutput, SearchWebOutput
from .exception import WebErrorCode, WebToolError


def _raise_web(code: WebErrorCode, message: str, *, cause: BaseException | None = None) -> None:
    """用统一的网络工具异常抛出失败；错误码供执行器和服务层判断。"""
    raise WebToolError(code, message, cause=cause)


_DEFAULT_SEARCH_ENDPOINT = "https://api.tavily.com/search"
_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_DEFAULT_MAX_REDIRECTS = 3
_USER_AGENT = "AgentSpace/0.1"
_UNSAFE_HOST_NAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.google.internal.",
    "instance-data",
    "instance-data.ec2.internal",
}


def _request_error_message(action: str, exc: Exception) -> WebToolError:
    if isinstance(exc, httpx.TimeoutException):
        return WebToolError(WebErrorCode.NETWORK_ERROR, f"{action}超时", cause=exc)
    if isinstance(exc, httpx.ConnectError):
        return WebToolError(WebErrorCode.NETWORK_ERROR, f"{action}无法连接服务", cause=exc)
    if isinstance(exc, httpx.RequestError):
        return WebToolError(WebErrorCode.NETWORK_ERROR, f"{action}网络请求失败", cause=exc)
    return WebToolError(WebErrorCode.NETWORK_ERROR, f"{action}失败", cause=exc)


def _safe_json_response(response: httpx.Response, action: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise WebToolError(WebErrorCode.RESPONSE_FORMAT_ERROR, f"{action}返回了无法解析的 JSON", cause=exc) from exc
    if not isinstance(payload, dict):
        _raise_web(WebErrorCode.RESPONSE_FORMAT_ERROR, f"{action}返回格式不正确")
    return payload


def search_web(
    query: str,
    max_results: int = 5,
    time_range: str = "any",
    *,
    api_key: str | None,
    endpoint: str = _DEFAULT_SEARCH_ENDPOINT,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    http_client: httpx.Client | None = None,
) -> SearchWebOutput:
    """通过服务端配置的 Tavily 兼容搜索 API 查找候选网页。"""
    if not api_key:
        _raise_web(WebErrorCode.CONFIGURATION_ERROR, "搜索服务未配置 API Key")
    if not query.strip() or len(query) > 512:
        _raise_web(WebErrorCode.INVALID_ARGUMENT, "query 必须为 1 到 512 个字符")
    if not 1 <= max_results <= 10:
        _raise_web(WebErrorCode.INVALID_ARGUMENT, "max_results 必须在 1 到 10 之间")
    if time_range not in {"any", "day", "week", "month"}:
        _raise_web(WebErrorCode.INVALID_ARGUMENT, "time_range 不受支持")

    payload = {
        "api_key": api_key,
        "query": query.strip(),
        "max_results": max_results,
    }
    if time_range != "any":
        payload["time_range"] = time_range

    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout_seconds)
    try:
        try:
            response = client.post(
                endpoint,
                json=payload,
                headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
            )
        except httpx.RequestError as exc:
            raise _request_error_message("搜索请求", exc) from exc

        if response.status_code in {401, 403}:
            _raise_web(WebErrorCode.AUTHENTICATION_FAILED, "搜索服务鉴权失败")
        if response.status_code == 429:
            _raise_web(WebErrorCode.RATE_LIMITED, "搜索服务请求次数超限")
        if response.status_code >= 500:
            _raise_web(WebErrorCode.DEPENDENCY_UNAVAILABLE, "搜索服务暂时不可用")
        if response.status_code >= 400:
            _raise_web(WebErrorCode.REMOTE_ERROR, f"搜索服务返回 HTTP {response.status_code}")

        data = _safe_json_response(response, "搜索服务")
        raw_results = data.get("results", [])
        if not isinstance(raw_results, list):
            _raise_web(WebErrorCode.RESPONSE_FORMAT_ERROR, "搜索服务返回的 results 格式不正确")

        results: list[dict[str, str | None]] = []
        for item in raw_results[:max_results]:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                continue
            result_url = item["url"].strip()
            parsed = urlsplit(result_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            results.append(
                {
                    "title": str(item.get("title") or ""),
                    "url": result_url,
                    "snippet": str(item.get("content") or item.get("snippet") or ""),
                    "source": parsed.hostname or "",
                    "published_at": (
                        str(item["published_date"])
                        if item.get("published_date") is not None
                        else None
                    ),
                }
            )

        return SearchWebOutput(
            query=query.strip(),
            results=results,
            returned_count=len(results),
            truncated=bool(data.get("truncated", False)),
        )
    finally:
        if owns_client:
            client.close()


def _is_unsafe_ip(value: str) -> bool:
    try:
        address = ip_address(value.split("%", 1)[0])
    except ValueError:
        return True
    return any(
        (
            address.is_loopback,
            address.is_private,
            address.is_link_local,
            address.is_reserved,
            address.is_multicast,
            address.is_unspecified,
        )
    )


def _validate_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        _raise_web(WebErrorCode.INVALID_ARGUMENT, "只允许访问 http 或 https URL")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        _raise_web(WebErrorCode.INVALID_ARGUMENT, "URL 必须包含合法主机名，且不能携带用户凭据")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in _UNSAFE_HOST_NAMES or hostname.endswith(".internal"):
        _raise_web(WebErrorCode.URL_NOT_ALLOWED, "目标地址不允许访问内部主机")
    try:
        addresses = {
            address[4][0]
            for address in socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError) as exc:
        raise WebToolError(WebErrorCode.NETWORK_ERROR, "无法解析目标主机", cause=exc) from exc
    if not addresses or any(_is_unsafe_ip(address) for address in addresses):
        _raise_web(WebErrorCode.URL_NOT_ALLOWED, "目标地址触发 SSRF 安全限制")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


class _HTMLExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title: str | None = None
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []
        self._skip_depth = 0
        self._links: list[dict[str, str]] = []
        self._media: list[dict[str, str]] = []
        self._current_link: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() in {"script", "style", "noscript", "template", "svg"}:
            self._skip_depth += 1
        if tag.lower() == "a" and attributes.get("href"):
            self._current_link = {"text": "", "url": urljoin(self.base_url, attributes["href"])}
        if tag.lower() == "img" and attributes.get("src"):
            self._media.append(
                {
                    "kind": "image",
                    "url": urljoin(self.base_url, attributes["src"]),
                    "alt": attributes.get("alt") or "",
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "template", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag.lower() == "a" and self._current_link is not None:
            self._current_link["text"] = " ".join(self._current_link["text"].split())
            self._links.append(self._current_link)
            self._current_link = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._current_link is not None:
            self._current_link["text"] += data
        if self._title_parts is not None:
            # title 文本也会由 handle_endtag 之后单独收集。
            pass
        if data.strip():
            self._text_parts.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def finish(self) -> tuple[str | None, str, list[dict[str, str]], list[dict[str, str]]]:
        # HTMLParser 没有统一的 title 回调；从已收集文本中无法安全区分标题，
        # 因此标题由 _extract_html 使用一个轻量正则式补充。
        text = " ".join(" ".join(self._text_parts).split())
        return self.title, text, self._links, self._media


def _extract_html(body: bytes, content_type: str, base_url: str) -> tuple[str | None, str, list[dict[str, str]], list[dict[str, str]]]:
    encoding = "utf-8"
    lowered = content_type.lower()
    if "charset=" in lowered:
        encoding = lowered.split("charset=", 1)[1].split(";", 1)[0].strip() or encoding
    try:
        text = body.decode(encoding, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    parser = _HTMLExtractor(base_url)
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:
        raise WebToolError(WebErrorCode.EXTRACTION_ERROR, "网页正文提取失败", cause=exc) from exc
    title = None
    lower = text.lower()
    start = lower.find("<title")
    if start >= 0:
        start = text.find(">", start)
        end = lower.find("</title>", start + 1) if start >= 0 else -1
        if start >= 0 and end >= 0:
            title = " ".join(text[start + 1:end].split()) or None
    _, visible_text, links, media = parser.finish()
    return title, visible_text, links, media


def fetch_url(
    url: str,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
    max_redirects: int = _DEFAULT_MAX_REDIRECTS,
    http_client: httpx.Client | None = None,
) -> FetchURLOutput:
    """读取一个受 SSRF 保护的 URL，并提取 HTML 或纯文本内容。"""
    if max_response_bytes <= 0 or max_redirects < 0:
        _raise_web(WebErrorCode.RESOURCE_LIMIT, "网络资源限制配置不合法")
    requested_url = _validate_url(url.strip())
    current_url = requested_url
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout_seconds, follow_redirects=False)
    try:
        for redirect_count in range(max_redirects + 1):
            current_url = _validate_url(current_url)
            request = client.build_request(
                "GET",
                current_url,
                headers={"Accept": "text/html, text/plain, application/json", "User-Agent": _USER_AGENT},
            )
            try:
                response = client.send(request, stream=True)
            except httpx.RequestError as exc:
                raise _request_error_message("网页请求", exc) from exc

            try:
                if 300 <= response.status_code < 400:
                    location = response.headers.get("location")
                    if not location:
                        _raise_web(WebErrorCode.REDIRECT_ERROR, "网页重定向缺少目标地址")
                    if redirect_count == max_redirects:
                        _raise_web(WebErrorCode.RESOURCE_LIMIT, "网页重定向次数超过限制")
                    current_url = urljoin(current_url, location)
                    continue
                if response.status_code == 404:
                    _raise_web(WebErrorCode.RESOURCE_NOT_FOUND, "网页不存在（HTTP 404）")
                if response.status_code in {401, 403}:
                    _raise_web(WebErrorCode.ACCESS_DENIED, f"网页拒绝访问（HTTP {response.status_code}）")
                if response.status_code >= 400:
                    _raise_web(WebErrorCode.REMOTE_ERROR, f"网页返回 HTTP {response.status_code}")

                content_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0].strip().lower()
                if content_type not in {"text/html", "application/xhtml+xml", "text/plain", "application/json"}:
                    _raise_web(WebErrorCode.CONTENT_UNSUPPORTED, f"暂不支持的内容类型：{content_type}")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_response_bytes:
                        body = body[:max_response_bytes]
                        truncated = True
                        break
                else:
                    truncated = False
                data = bytes(body)
                if content_type in {"text/html", "application/xhtml+xml"}:
                    title, text, links, media = _extract_html(data, content_type, current_url)
                else:
                    try:
                        text = data.decode("utf-8", errors="replace")
                    except UnicodeError as exc:
                        raise WebToolError(WebErrorCode.EXTRACTION_ERROR, "网页文本解码失败", cause=exc) from exc
                    title, links, media = None, [], []
                return FetchURLOutput(
                    requested_url=requested_url,
                    final_url=current_url,
                    title=title,
                    content_type=content_type,
                    text=text,
                    links=links,
                    media=media,
                    truncated=truncated,
                    extraction_status="completed",
                )
            finally:
                response.close()
        _raise_web(WebErrorCode.RESOURCE_LIMIT, "网页重定向次数超过限制")
    finally:
        if owns_client:
            client.close()

