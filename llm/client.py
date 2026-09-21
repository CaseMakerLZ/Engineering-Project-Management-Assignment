import os

from dotenv import load_dotenv
from openai import AsyncOpenAI
from openai.types.responses import Response
from typing import Any

load_dotenv()
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID")
TIMEOUT=200

class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=LLM_API_KEY,base_url=LLM_BASE_URL,timeout=TIMEOUT)
        self.model = LLM_MODEL_ID

    async def generate(self,input,tools: list[dict[str,Any]] | None = None) -> Response:
        response = await self.client.responses.create(
            model=self.model,
            input=input,
            tools=tools
        )
        return response


