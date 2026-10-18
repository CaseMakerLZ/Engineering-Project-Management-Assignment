from openai import AsyncOpenAI
from openai.types.responses import Response
from typing import Any

class LLMClient:
    """调用模型的客户端；配置由上层统一读取后传入。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 200.0,
    ):
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

    async def generate(self,input,tools: list[dict[str,Any]] | None = None) -> Response:
        response = await self.client.responses.create(
            model=self.model,
            input=input,
            tools=tools
        )
        return response


