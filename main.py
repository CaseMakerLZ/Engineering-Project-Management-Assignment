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

def calculator(a: float,b: float,operation: str) -> float:
    if operation == "add":
        return a + b
    elif operation == "subtract":
        return a - b
    elif operation == "multiply":
        return a * b
    elif operation == "divide":
        if b == 0:
            raise ZeroDivisionError
        return a / b
    else:
        raise ValueError(f"{operation} is not a valid operation")

class CalculatorArgs(BaseModel):
    a : float
    b : float
    operation : Literal["add", "subtract", "multiply", "divide"]



if __name__ == "__main__":
    registry: ToolRegistry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="calculator",
            description="执行基本四则运算",
            parameters=CalculatorArgs.model_json_schema(),
            function=calculator,
        )
    )

    tool: ToolDefinition = registry.get("calculator")
    result: float = tool.function(a=10,b=1.1,operation="add")
    print(result)

