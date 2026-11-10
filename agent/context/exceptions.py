"""上下文整理的可公开结束原因，不携带供应商异常或服务端路径。"""


CONTEXT_TOO_LARGE = "上下文超过本次输入预算，无法安全继续；完整过程和已产生的文件保留。"
CONTEXT_COMPACTION_FAILED = "上下文整理未成功，未替换原始记录；完整过程和已产生的文件保留。"
CONTEXT_COUNT_FAILED = "无法按配置完成输入计数，请检查模型服务的计数能力；已产生的文件保留。"


class ContextError(RuntimeError):
    """预算不足、计数失败或整理失败；Runtime按可控失败保存已有过程。"""

