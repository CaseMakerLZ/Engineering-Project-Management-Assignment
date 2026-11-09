"""Agent 自身的结束原因，不依赖 HTTP 或数据库。"""

import re


AGENT_FAILURE = "Agent执行失败，请查看本次运行的过程记录；已产生的文件保留。"
INTERRUPTED_FAILURE = "运行协程被中断，任务未完整结束；已产生的文件保留。"


def public_failure_message(error: str | None) -> str:
    """只公开本地定义的说明；旧库及外部异常原文一律回退，不做字符串前缀放行。"""
    from .context.exceptions import CONTEXT_TOO_LARGE, CONTEXT_COMPACTION_FAILED, CONTEXT_COUNT_FAILED
    if error in (AGENT_FAILURE, INTERRUPTED_FAILURE, CONTEXT_TOO_LARGE,
                 CONTEXT_COMPACTION_FAILED, CONTEXT_COUNT_FAILED,
                 "隔离执行环境不可用或文件检查未通过；未在宿主机执行命令，已产生的合格文件尽力保留。",
                 "隔离执行名额已满，请稍后重试。",
                 "部分隔离文件写回失败或存在版本冲突；请查看文件写回记录，已成功写回的文件保留。"):
        return error
    if isinstance(error, str) and re.fullmatch(
        r"已达到本次执行上限（[1-9][0-9]{0,8}轮），任务未完整结束；已产生的文件保留。", error
    ):
        return error
    return "任务执行失败，请通过运行 ID 查看服务端诊断"


class AgentLoopLimitError(RuntimeError):
    """循环名额已经用完，本轮不能再请求模型；已执行的工具不会回滚。"""

    def __init__(self, max_steps: int) -> None:
        super().__init__(
            f"已达到本次执行上限（{max_steps}轮），任务未完整结束；已产生的文件保留。"
        )
