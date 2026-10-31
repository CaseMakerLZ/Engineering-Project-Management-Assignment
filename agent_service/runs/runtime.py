# 这个文件把正式 HTTP 服务连接到现有的 Agent Core。
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3
from functools import wraps
from typing import Any, Callable, Protocol

from agent.agent import Agent
from agent.context import ContextBuilder
from agent.loop import AgentLoop
from agent.message import AgentMessage, MessageType
from ..config import Settings
from ..workspace.exception import WorkspaceError
from ..workspace.policy import is_valid_identifier, resolve_project_directory
from llm.client import LLMClient
from tools.executor import ToolExecutor, ToolExecutionResult
from tools.bootstrap import create_default_registry
from tools.exceptions import ToolError, ToolErrorCode


@dataclass(slots=True)
class RuntimeResult:
    # Agent 执行结束后返回最终回答和本次运行的过程消息。
    result: str
    messages: list[AgentMessage]


class AgentRuntime(Protocol):
    """所有 Agent 运行方式都需要提供的统一调用方法。"""
    async def run(
        self,
        prompt: str,
        project_id: str | None = None,
        context: list[dict[str, Any]] | None = None,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
        created_at: datetime | None = None,
        on_text: Callable[[str, str], None] | None = None,
        on_tool_started: Callable[[str, str], None] | None = None,
        on_tool_finished: Callable[[str, str, ToolExecutionResult], None] | None = None,
    ) -> RuntimeResult:
        ...


def resolve_project_root(
    settings: Settings,
    project_id: str | None,
    *,
    repository: Any | None = None,
) -> Path:
    """根据运行模式解析本次任务实际允许访问的项目目录。

    本地模式继续读共享 SQLite 的 ``project.local_path``；云端模式先用
    ``project_id`` 查可信的 ``owner_id``，再拼
    ``workspace_root/users/{owner_id}/projects/{project_id}``。

    云端目录不由模型或浏览器指定：即使收到一个格式合法的 project_id，也要先
    有数据库里的归属记录才算数。``repository`` 只在云端模式需要。
    """
    mode = settings.execution_mode.lower()
    if mode == "local":
        return _resolve_local_project_from_database(settings, project_id)

    if mode == "cloud":
        return _resolve_cloud_project_root(settings, project_id, repository)

    raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "AGENT_SERVICE_EXECUTION_MODE 只能是 local 或 cloud")


def _resolve_cloud_project_root(
    settings: Settings, project_id: str | None, repository: Any | None
) -> Path:
    """云端项目目录：归属来自数据库，路径由服务端拼，逐层查链接。"""
    if project_id is None:
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "云端运行必须提供 project_id")
    if not is_valid_identifier(project_id):
        raise ToolError(
            ToolErrorCode.CONFIGURATION_ERROR, "project_id 只能包含字母、数字、下划线和连字符"
        )
    if repository is None:
        # 没有归属查询就无法确定 users/{user_id} 这一层，宁可拒绝也不猜目录。
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "云端运行需要项目归属查询")

    try:
        owner_id = repository.get_project_owner(project_id)
    except Exception as exc:
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "无法读取项目归属") from exc
    if not owner_id:
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "项目不存在或未绑定所有者")
    if not is_valid_identifier(owner_id):
        # owner 不是可用的单层目录名时按"没有可用归属"处理，不把内部布局细节
        # 暴露给调用方；这条同时挡住了从数据库写入斜杠/点路径的异常数据。
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "项目不存在或未绑定所有者")

    root = Path(settings.workspace_root).expanduser()
    if not root.is_dir():
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "云端工作区根目录不存在或不是目录")

    try:
        project_root = resolve_project_directory(root, owner_id, project_id)
    except WorkspaceError as exc:
        # 工作区域异常在这里收敛成 ToolError，保持 Runtime 对外抛错类型不变。
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, exc.public_message()) from exc

    if not project_root.is_dir():
        raise ToolError(
            ToolErrorCode.CONFIGURATION_ERROR, "云端项目工作区不存在，请先准备工作区"
        )
    return project_root.resolve()


def _resolve_local_project_from_database(settings: Settings, project_id: str | None) -> Path:
    """从 Java 与 Python 共用的 SQLite 查找本地项目目录。

    项目由 Java 创建并写入 project.local_path。缺少数据库、项目或有效目录
    时直接报配置错误，不从 TOML 或当前工作目录猜测路径。
    """
    if project_id is None:
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地运行必须提供 project_id")
    database_path = Path(settings.sqlite_database_path).expanduser().resolve()
    if not database_path.is_file():
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地项目数据库不存在")
    try:
        connection = sqlite3.connect(database_path, timeout=2.0)
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'project'"
            ).fetchone()
            if table is None:
                raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地项目表不存在，请先由 Java 初始化")
            row = connection.execute(
                "SELECT local_path FROM project WHERE id = ?", (project_id,)
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "无法读取本地项目数据库") from exc

    if row is None:
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "请求的本地项目不存在")
    local_path = row[0]
    if not isinstance(local_path, str) or not local_path.strip():
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地项目未绑定有效目录")
    project_root = Path(local_path).expanduser().resolve()
    if not project_root.is_dir():
        raise ToolError(ToolErrorCode.CONFIGURATION_ERROR, "本地项目目录不存在或不是目录")
    return project_root


class CurrentAgentRuntime:
    """使用当前手写 Agent Core 执行任务。"""

    def __init__(self, settings: Settings, repository: Any | None = None) -> None:
        self.settings = settings
        # 与 RunService 共用同一个仓储，保证历史读取和快照更新使用同一数据源。
        self.repository = repository

    # 以后替换 Agent 实现时，只需要增加新的 Runtime，不用修改任务服务。
    async def run(
        self,
        prompt: str,
        project_id: str | None = None,
        context: list[dict[str, Any]] | None = None,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
        created_at: datetime | None = None,
        on_text: Callable[[str, str], None] | None = None,
        on_tool_started: Callable[[str, str], None] | None = None,
        on_tool_finished: Callable[[str, str, ToolExecutionResult], None] | None = None,
    ) -> RuntimeResult:
        #组装Agent
        # SSE 第一步仅预留可见文字回调；后续接模型流时才调用，不能拆分最终结果假装流式。
        # 第二步已经接通：下方把 on_text 交给 Agent，再经 AgentLoop 传到模型客户端。
        llm = LLMClient(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            model=self.settings.llm_model_id,
            timeout_seconds=self.settings.llm_timeout_seconds,
        )
        project_root = resolve_project_root(
            self.settings, project_id, repository=self.repository
        )
        registry = create_default_registry(
            project_root=project_root,
            web_api_key=self.settings.web_api_key,
            memory_repository=self.repository,
            memory_project_id=project_id,
            memory_conversation_id=conversation_id,
            memory_before_created_at=created_at,
            memory_run_id=run_id,
        )
        if self.settings.execution_mode.lower() == "cloud":
            # Git 元数据只由服务端维护；文件工具不能读取/改写它（含 Windows 大小写）。
            for tool in registry.get_all():
                if tool.name in {"read_text_file", "write_text_file", "edit_text_file", "list_directory", "search_text"}:
                    tool.function = _protect_git_metadata(tool.function)
        executor = ToolExecutor(registry)
        loop = AgentLoop(llm, registry, executor)
        agent = Agent(loop)

        # 新运行链路由 Python 根据 agent_run 身份组装上下文；缺少身份信息时
        # 才兼容旧的 Java context 调用。
        if (
            self.repository is not None
            and project_id is not None
            and run_id is not None
            and created_at is not None
        ):
            snapshot = ContextBuilder(self.repository).build(
                project_id=project_id,
                conversation_id=conversation_id,
                current_created_at=created_at,
                project_root=project_root,
            )
            initial_messages: list[AgentMessage] = []
            # 系统提示词的注入位置：当前为空，未来可直接填入全局规则。
            if snapshot.system_prompt.strip():
                initial_messages.append(
                    AgentMessage(MessageType.SYSTEM, snapshot.system_prompt)
                )
            if snapshot.project_instructions:
                initial_messages.append(
                    AgentMessage(
                        MessageType.PROJECT_INSTRUCTIONS,
                        snapshot.project_instructions,
                    )
                )
            initial_messages.extend(snapshot.messages)
            # 保存本轮真正使用的初始上下文，而不是 Java 请求中的旧快照。
            self.repository.update_context(
                run_id,
                [_message_to_context(message) for message in initial_messages],
            )
        else:
            # 兼容旧的测试或内部调用。
            initial_messages = [
                AgentMessage(
                    type=MessageType.USER
                    if message["role"] == "user"
                    else MessageType.ASSISTANT,
                    content=message["content"],
                )
                for message in context or []
            ]

        for message in initial_messages:
            agent.state.add(message)
        initial_history_length = len(initial_messages)
        result = await agent.run(
            prompt, on_text=on_text,
            on_tool_started=on_tool_started, on_tool_finished=on_tool_finished,
        )
        # 历史消息只帮助本轮回答，不重复保存为本轮新消息。
        return RuntimeResult(
            result=result,
            messages=agent.state.get_history()[initial_history_length:],
        )


def _message_to_context(message: AgentMessage) -> dict[str, Any]:
    """将 Agent 内部消息转换为可写入 context_json 的通用结构。"""
    role_by_type = {
        MessageType.SYSTEM: "system",
        MessageType.PROJECT_INSTRUCTIONS: "developer",
        MessageType.USER: "user",
        MessageType.ASSISTANT: "assistant",
        MessageType.REASONING: "reasoning",
        MessageType.TOOL_CALL: "tool_call",
        MessageType.TOOL_RESULT: "tool_result",
    }
    return {"role": role_by_type[message.type], "content": message.content}


def _protect_git_metadata(function):
    """不改变工具参数，只拒绝模型直接指定版本库内部路径。"""
    @wraps(function)
    def protected(**kwargs):
        path = str(kwargs.get("file", kwargs.get("directory", "."))).replace("\\", "/")
        if any(part.split(":", 1)[0].rstrip(" .").casefold() == ".git"
               for part in path.split("/")):
            raise ToolError(ToolErrorCode.INVALID_ARGUMENT, "不能访问服务端版本记录目录")
        return function(**kwargs)
    return protected
