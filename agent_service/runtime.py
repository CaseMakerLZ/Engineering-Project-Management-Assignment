# 这个文件把正式 HTTP 服务连接到现有的 Agent Core。
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from typing import Protocol

from agent.agent import Agent
from agent.loop import AgentLoop
from agent.message import AgentMessage, MessageType
from .config import Settings
from llm.client import LLMClient
from tools.executor import ToolExecutor
from tools.bootstrap import create_default_registry
from tools.exceptions import ToolError, ToolErrorCode


@dataclass(slots=True)
class RuntimeResult:
    # Agent 执行结束后返回最终回答和本次运行的过程消息。
    result: str
    messages: list[AgentMessage]


class AgentRuntime(Protocol):
    """所有 Agent 运行方式都需要提供的统一调用方法。"""
    async def run(self, prompt: str, project_id: str | None = None, context: list[dict[str, str]] | None = None) -> RuntimeResult:
        ...


def resolve_project_root(settings: Settings, project_id: str | None) -> Path:
    """根据运行模式解析本次任务实际允许访问的项目目录。"""
    mode = settings.execution_mode.lower()
    if mode == "local":
        database_root = _resolve_local_project_from_database(settings, project_id)
        if database_root is not None:
            return database_root

        # 兼容迁移前只在 TOML 中配置项目的本地运行方式。
        if settings.local_projects:
            if project_id is None:
                raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地运行必须提供 project_id")
            project_root_value = settings.local_projects.get(project_id)
            if project_root_value is None:
                raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "请求的本地项目不存在")
            project_root = Path(project_root_value).expanduser().resolve()
            if not project_root.is_dir():
                raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地项目目录不存在或不是目录")
            return project_root

        # 兼容迁移前的单项目 Settings；新的配置应使用 TOML local.projects。
        if not settings.local_project_id or not settings.local_project_root:
            raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地运行必须配置项目 ID 和项目目录")
        if project_id != settings.local_project_id:
            raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "请求项目与本地绑定的项目不一致")
        project_root = Path(settings.local_project_root).expanduser().resolve()
        if not project_root.is_dir():
            raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地项目目录不存在或不是目录")
        return project_root

    if mode == "cloud":
        if project_id is None:
            raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "云端运行必须提供 project_id")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
            raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "project_id 只能包含字母、数字、下划线和连字符")
        root = Path(settings.workspace_root).expanduser().resolve()
        if not root.is_dir():
            raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "云端工作区根目录不存在或不是目录")
        project_path = root / project_id
        if project_path.is_symlink():
            raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "云端项目工作区不能是符号链接")
        project_root = project_path.resolve()
        if not project_root.is_relative_to(root) or not project_root.is_dir():
            raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "云端项目工作区不存在或不在工作区根目录内")
        return project_root

    raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "AGENT_SERVICE_EXECUTION_MODE 只能是 local 或 cloud")


def _resolve_local_project_from_database(settings: Settings, project_id: str | None) -> Path | None:
    """从 Java 与 Python 共用的 SQLite 查找本地项目目录。

    返回 None 表示数据库尚未有项目表或没有对应项目，此时调用方可以使用
    旧的 TOML 映射完成兼容迁移；找到记录但目录非法时直接报错，避免悄悄
    回退到另一个错误目录。
    """
    if project_id is None:
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地运行必须提供 project_id")
    database_path = Path(settings.sqlite_database_path).expanduser().resolve()
    if not database_path.is_file():
        return None
    try:
        connection = sqlite3.connect(database_path, timeout=2.0)
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'project'"
            ).fetchone()
            if table is None:
                return None
            row = connection.execute(
                "SELECT local_path FROM project WHERE id = ?", (project_id,)
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "无法读取本地项目数据库") from exc

    if row is None:
        return None
    local_path = row[0]
    if not isinstance(local_path, str) or not local_path.strip():
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地项目未绑定有效目录")
    project_root = Path(local_path).expanduser().resolve()
    if not project_root.is_dir():
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地项目目录不存在或不是目录")
    return project_root


class CurrentAgentRuntime:
    """使用当前手写 Agent Core 执行任务。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # 以后替换 Agent 实现时，只需要增加新的 Runtime，不用修改任务服务。
    async def run(self, prompt: str, project_id: str | None = None, context: list[dict[str, str]] | None = None) -> RuntimeResult:
        #组装Agent
        llm = LLMClient(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            model=self.settings.llm_model_id,
            timeout_seconds=self.settings.llm_timeout_seconds,
        )
        project_root = resolve_project_root(self.settings, project_id)
        registry = create_default_registry(
            project_root=project_root,
            web_api_key=self.settings.web_api_key,
        )
        executor = ToolExecutor(registry)
        loop = AgentLoop(llm, registry, executor)
        agent = Agent(loop)
        #Python 遍历 Java 传来的上下文
        for message in context or []:
            message_type = MessageType.USER if message["role"] == "user" else MessageType.ASSISTANT
            agent.state.add(AgentMessage(type=message_type, content=message["content"]))
        result = await agent.run(prompt)
        # 历史消息只帮助本轮回答，不重复保存为本轮新消息。
        return RuntimeResult(result=result, messages=agent.state.get_history()[len(context or []):])
