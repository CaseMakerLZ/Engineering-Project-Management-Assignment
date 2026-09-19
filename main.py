import asyncio

from agent.agent import Agent
from llm.client import LLMClient
from tools.registry import ToolRegistry,ToolDefinition
from pydantic import BaseModel
from typing import Literal

async def main():
    llm = LLMClient()
    agent = Agent(llm)
    result = await agent.run("请介绍一下软件工程中的接口文档的规范制作方式")
    print("="*50)
    print(result)
    print("=" * 50)




if __name__ == "__main__":
    asyncio.run(main())

