import asyncio
from pathlib import Path

from agent.agent import Agent
from agent.loop import AgentLoop
from agent_service.config import Settings
from llm.client import LLMClient
from tools.bootstrap import create_default_registry
from tools.executor import ToolExecutor


async def main():
    settings = Settings.from_environment()
    llm = LLMClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model_id,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    registry = create_default_registry(
        workspace_root=Path(__file__).resolve().parent,
        web_api_key=settings.web_api_key,
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

