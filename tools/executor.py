import json

from typing import Any
from tools.registry import ToolRegistry

class ToolExecutor:
    def __init__(self,registry: ToolRegistry):
        self.registry = registry

    def execute(self,tool_name: str,arguments: str) -> Any:
        tool = self.registry.get(tool_name)
        args: dict[str,Any] = json.loads(arguments)
        result = tool.function(**args)
        return result

