from typing import Any,Callable,Type

from pydantic import BaseModel


class ToolDefinition:
    def __init__(self,
                 name: str,
                 description: str,
                 args_model: Type[BaseModel],#this stands for a BaseModel class,instead of a reality of BaseModel
                 function: Callable[...,Any]
                 ) -> None:
        self.name: str = name
        self.description: str = description
        self.args_model: Type[BaseModel] = args_model
        self.function: Callable[...,Any] = function

    def get_parameters_schema(self) -> dict[str,Any]:
        return self.args_model.model_json_schema()

#Tool注册表封装，现在可以看作一个tool的管理中心，它可以通过register方法加入新的工具，也可通过get方法获取相关工具的信息
class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str,ToolDefinition] = {}

    def register(self,tool: ToolDefinition):
        self._tools[tool.name] = tool

    def get(self,name: str) -> ToolDefinition:
        return self._tools[name]

    def get_all(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get_llm_tools(self) -> list[dict[str,Any]]:
        return [
            {
                "type":"function",
                "name":tool.name,
                "description": tool.description,
                "parameters": tool.get_parameters_schema()
            }
            for tool in self._tools.values()
        ]
