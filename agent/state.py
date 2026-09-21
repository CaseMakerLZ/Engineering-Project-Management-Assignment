#状态（state）：本质就是模型当前知道了什么，管理状态的意义在于让agent有agent loop的工作能力。
#踩过的坑：对于openai的apikey，可以用previous_id来自动管理，但是其他的模型就不能这样处理，需要手动管理
from dataclasses import dataclass,field
from enum import Enum
from typing import Any

from agent.message import AgentMessage


class AgentStatus(str,Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_STEPS_EXCEEDED = "max_steps_exceeded"

@dataclass
class AgentState:
    #这里list[Any]的处理其实依旧很粗糙：里面可能存在多种类型str,dict,ResponseOutputMessage....,但这里先不管，之后再处理
    history: list[AgentMessage] = field(default_factory=list)
    step: int = 0
    max_steps: int = 20
    status: AgentStatus = AgentStatus.CREATED
    last_tool_result: Any = None

    def add(self,message: AgentMessage) -> None:
        self.history.append(message)

    def get_history(self) -> list[AgentMessage]:
        return self.history

    def increment_step(self) -> None:
        self.step += 1

    def can_continue(self) -> bool:
        return self.step < self.max_steps

