import json

from typing import Any
from tools.registry import ToolRegistry

class ToolExecutor:
    def __init__(self,registry: ToolRegistry):
        self.registry = registry

    def execute(self,tool_name: str,arguments: str) -> Any:
        tool = self.registry.get(tool_name)
        #先初步将传入的json字符串转化为参数字典
        raw_args: dict[str,Any] = json.loads(arguments)
        #校验参数字典(实际上左边是一个解析后的对象，若解析成功就成功构建对象，否则会抛异常，无法执行下去)
        #假如抛异常，我暂时不处理它，之后再构建完整的异常体系
        validated_args = tool.args_model.model_validate(raw_args)
        #将得到的对象先通过model.dump化为字典格式，再用**解包成参数列表
        result = tool.function(**validated_args.model_dump())
        return result

