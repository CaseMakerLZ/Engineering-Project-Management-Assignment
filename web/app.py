from fastapi import FastAPI

from agent.loop import AgentLoop
from llm.client import LLMClient
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry
from agent.agent import Agent

app = FastAPI(title="Agent_Core")

def build_agent() -> Agent:
    registry: ToolRegistry = ToolRegistry()
    executor: ToolExecutor = ToolExecutor(registry=registry)
    llm = LLMClient()
    loop: AgentLoop = AgentLoop(llm=llm,registry=registry,executor=executor)
    agent: Agent = Agent(loop)

    return agent

@app.post("/RunAgent")
async def run_agent():
    agent: Agent = build_agent()
    res = await agent.run("介绍一下软件测试的相关知识")
