#状态（state）：本质就是模型当前知道了什么，管理状态的意义在于让agent有agent loop的工作能力。
#踩过的坑：对于openai的apikey，可以用previous_id来自动管理，但是其他的模型就不能这样处理，需要手动管理
from dataclasses import dataclass,field

@dataclass
class AgentState:
    history: list = field(default_factory=list)

    def add(self,item:dict) -> None:
        self.history.append(item)

    def get_history(self) -> list:
        return self.history

