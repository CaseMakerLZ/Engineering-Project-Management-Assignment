import asyncio
from pathlib import Path

from agent.agent import Agent
from agent.loop import AgentLoop
from llm.client import LLMClient
from tools.bootstrap import create_default_registry
from tools.executor import ToolExecutor


async def main():
    llm = LLMClient()
    registry = create_default_registry(
        workspace_root=Path(__file__).resolve().parent,
    )
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

