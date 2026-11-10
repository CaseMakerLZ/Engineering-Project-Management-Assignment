"""计数只回答“多大”，不负责决定删什么。估算与服务端计数明确区分。"""

import asyncio
import json
import logging
import math

from .exceptions import CONTEXT_COUNT_FAILED, ContextError


logger = logging.getLogger(__name__)


class TokenCounter:
    """每个任务独有：默认先问服务端；不支持时使用有余量的本地估算。

    本地分词对整个JSON请求计数，包含工具及消息结构，但仍不是供应商的实际渲染。
    不同模型、图片、加密reasoning都不能宣称精确；未知分词或不可读字段按字节保守计算。
    usage只能校准之后的估算，不能保证已经发出的请求永不超限。
    """

    def __init__(self, client, *, mode="auto", encoding="cl100k_base"):
        self.client = client
        self.mode = mode
        self.encoding = encoding
        self.source = "estimate"
        self._server_unavailable = False
        self._warned = False
        self._encoder = None
        self._encoding_checked = False
        self._factor = 1.3
        self._last_local = 0

    def estimate(self, input, tools) -> int:
        """可在工作线程执行；特殊token字符串按普通文本处理，不让文件内容触发异常。"""
        payload = json.dumps({"input": input, "tools": tools}, ensure_ascii=False, default=str)
        if not self._encoding_checked:
            self._encoding_checked = True
            try:
                import tiktoken
                self._encoder = tiktoken.get_encoding(self.encoding)
            except Exception:
                # 离线未安装/无缓存时不因此失去预算保护；字节估算更早触发整理。
                self._encoder = None
        base = (len(self._encoder.encode(payload, disallowed_special=()))
                if self._encoder is not None else len(payload.encode("utf-8")))
        # 加密字段不能按普通文本分词宣称准确，至少按其字节量留出余量。
        def opaque_size(value):
            if isinstance(value, dict):
                return sum(len(str(item).encode("utf-8")) if key == "encrypted_content"
                           else opaque_size(item) for key, item in value.items())
            if isinstance(value, list):
                return sum(opaque_size(item) for item in value)
            return 0
        base += opaque_size(input)
        self._last_local = max(1, base)
        return math.ceil(base * self._factor) + 128

    async def count(self, input, tools) -> int:
        """server模式严格要求计数接口；auto仅在明确不支持时退回估算，不掩盖鉴权故障。"""
        estimate = await asyncio.to_thread(self.estimate, input, tools)
        method = getattr(self.client, "count_input_tokens", None)
        if self.mode != "estimate" and not self._server_unavailable and method is not None:
            try:
                value = await method(input=input, tools=tools)
            except NotImplementedError:
                self._server_unavailable = True
            except Exception as exc:
                raise ContextError(CONTEXT_COUNT_FAILED) from exc
            else:
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ContextError(CONTEXT_COUNT_FAILED)
                self.source = "server"
                return value
        if self.mode == "server":
            raise ContextError(CONTEXT_COUNT_FAILED)
        self.source = "estimate"
        if not self._warned:
            logger.warning("上下文使用本地保守估算，不保证与模型实际token数完全一致")
            self._warned = True
        return estimate

    def observe(self, response) -> None:
        """按供应商实际用量向上校准，不因某次估算偏大而减小安全余量。"""
        usage = getattr(response, "usage", None)
        actual = (usage.get("input_tokens") if isinstance(usage, dict)
                  else getattr(usage, "input_tokens", None))
        if isinstance(actual, int) and not isinstance(actual, bool) and actual > 0 and self._last_local:
            self._factor = max(self._factor, actual / self._last_local * 1.15)
