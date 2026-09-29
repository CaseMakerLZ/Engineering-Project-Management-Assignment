import asyncio

from agent.agent import Agent
from agent.loop import AgentLoop
from llm.client import LLMClient
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry


async def main():
    llm = LLMClient()
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    loop = AgentLoop(llm,registry,executor)
    agent = Agent(loop)
    #agent = Agent(llm)
    result = await agent.run("请介绍一下软件工程中的接口文档的规范制作方式")
    print("="*50)
    print(result)
    print("=" * 50)




if __name__ == "__main__":
    asyncio.run(main())

