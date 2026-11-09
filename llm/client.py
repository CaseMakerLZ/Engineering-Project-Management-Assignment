from openai import AsyncOpenAI
from openai.types.responses import Response
from typing import Any, Callable, Dict
from openai import APIStatusError

class LLMClient:
    """调用模型的客户端；配置由上层统一读取后传入。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 200.0,
    ) -> None:
        """按传入配置创建 SDK 客户端；缺参时回退到统一 Settings 读取。"""

        # 兼容旧的本地学习脚本：无参数调用仍从统一 Settings 读取，
        # 不再自行寻找 llm/.env。
        if api_key is None or base_url is None or model is None:
            from agent_service.config import Settings

            settings = Settings.from_environment()
            api_key = api_key if api_key is not None else settings.llm_api_key
            base_url = base_url if base_url is not None else settings.llm_base_url
            model = model if model is not None else settings.llm_model_id
            if timeout_seconds == 200.0:
                timeout_seconds = settings.llm_timeout_seconds
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )
        self.model = model

    async def close(self) -> None:
        """关闭底层 HTTP 连接池，由应用关闭时调用一次。

        不改变模型、供应商或 SDK 调用方式；重复调用安全（httpx 的关闭是幂等的）。
        """

        await self.client.close()

    async def generate(
        self, input, tools: list[dict[str, Any]] | None = None,
        *, on_text: Callable[[str, str], None] | None = None,
        max_output_tokens: int | None = None,
    ) -> Response:
        """on_text只是一个函数，不传 on_text 就等完整回答；传入则边收文字边交出去，最后仍返回完整回答。

        on_text 接收两个值：这段文字所属的消息 ID、刚收到的文字。
        它应快速处理文字，不在里面执行耗时操作；本方法不会把文字重复写入历史。
        """
        limits = ({"max_output_tokens": max_output_tokens, "truncation": "disabled"}
                  if max_output_tokens is not None else {})
        if on_text is None:
            response = await self.client.responses.create(
                model=self.model,
                input=input,
                tools=tools,
                **limits,
            )
            if response.status not in (None, "completed"):
                raise RuntimeError("模型未完整生成回答")
            return response

        stream = await self.client.responses.create(
            model=self.model,
            input=input,
            tools=tools,
            stream=True,
            **limits,
        )
        # 即使中途报错或调用方停止等待，也要关闭这次网络连接。
        async with stream:
            async for event in stream:
                if event.type == "response.output_text.delta":
                    # 这里只交出正文，不把工具参数、reasoning 等通知当作文字展示。
                    on_text(event.item_id, event.delta)
                elif event.type == "response.completed":
                    # 结束通知中已有完整 Response；原工具调用/历史处理可以继续使用它。
                    if event.response.status != "completed":
                        raise RuntimeError("模型未完整生成回答")
                    return event.response
                elif event.type in {"response.failed", "response.incomplete", "error"}:
                    raise RuntimeError(f"模型生成未成功结束：{event.type}")

        # 网络结束不代表模型完成，不能把已经显示的几段文字冒充最终回答。
        raise RuntimeError("模型连接已结束，但未收到完整回答结束通知")

    async def count_input_tokens(self, *, input, tools) -> int:
        """同一供应商的计数接口；当前SDK通过通用post适配，不换服务商。

        只有404/405/501视为不支持；鉴权/限流/网络故障不能伪装成接口不支持。
        """
        try:
            result = await self.client.with_options(max_retries=0).post(
                "/responses/input_tokens", cast_to=Dict[str, Any],
                body={"model": self.model, "input": input, "tools": tools},
            )
        except APIStatusError as exc:
            if exc.status_code in {404, 405, 501}:
                raise NotImplementedError("模型服务未提供计数接口") from exc
            raise
        value = result.get("input_tokens")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("模型服务未返回有效计数")
        return value


