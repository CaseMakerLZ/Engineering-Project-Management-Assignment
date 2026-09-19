from typing import Any,Callable,Type

class ToolDefinition:
    def __init__(self,
                 name: str,
                 description: str,
                 parameters: dict[str,Any],
                 function: Callable[...,Any]
                 ) -> None:
        self.name: str = name
        self.description: str = description
        self.parameters: dict[str,Any] = parameters
        self.function: Callable[...,Any] = function

#Tool注册表封装，现在可以看作一个tool的管理中心，它可以通过register方法加入新的工具，也可通过get方法获取相关工具的信息
class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str,ToolDefinition] = {}

    def register(self,tool: ToolDefinition):
        self._tools[tool.name] = tool

    def get(self,name: str) -> ToolDefinition:
        return self._tools[name]

    def get_all(self) -> list[ToolDefinition]:
        return list[self._tools.values()]
