# 这个文件把正式 HTTP 服务连接到现有的 Agent Core。
from dataclasses import dataclass
import asyncio
import logging
from datetime import datetime
from pathlib import Path
import sqlite3
import threading
from functools import wraps, partial
from typing import Any, Callable, Protocol

from agent.agent import Agent
from agent.context import ContextBuilder
from agent.context.manager import ContextManager, ContextPolicy
from agent.context.tokens import TokenCounter
from agent.context.exceptions import ContextError
from agent.loop import AgentLoop
from agent.message import AgentMessage, MessageType
from agent.state import AgentStatus
from agent.exception import AgentLoopLimitError, AGENT_FAILURE, INTERRUPTED_FAILURE
from ..config import Settings
from ..workspace.exception import WorkspaceError
from ..workspace.policy import is_valid_identifier, resolve_project_directory
from llm.client import LLMClient
from tools.executor import ToolExecutor, ToolExecutionResult
from tools.bootstrap import create_default_registry
from tools.exceptions import ToolError, ToolErrorCode
from tools.terminal.sandbox import ContainerExecutor, SandboxLimits
from tools.terminal.workspace import SandboxWorkspace, WorkspaceLimits

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class RuntimeResult:
    # Agent 执行结束后返回最终回答和本次运行的过程消息。
    result: str
    messages: list[AgentMessage]
    # 无错误时保持旧的两个参数用法；失败时仍带回本轮已有消息供批量保存。
    error: str | None = None
    interrupted: bool = False


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

    def __init__(
        self, settings: Settings,
        repository: Any | None = None,
        llm_client: Any | None = None,
    ) -> None:
        """保存配置、仓储与共享模型客户端；构造时不连库、不建网络连接。"""

        self.settings = settings
        # 与 RunService 共用同一个仓储，保证历史读取和快照更新使用同一数据源。
        self.repository = repository
        # 应用级共享模型客户端；为 None 时退回每个任务创建一次（测试与单脚本）。
        self.llm_client = llm_client
        self._sandbox_slots = threading.BoundedSemaphore(settings.sandbox_max_concurrent)
        self._sandbox_unhealthy = False

    async def run(self, prompt: str, project_id: str | None = None,
                  context: list[dict[str, Any]] | None = None, *, run_id: str | None = None,
                  conversation_id: str | None = None, created_at: datetime | None = None,
                  on_text=None, on_tool_started=None, on_tool_finished=None) -> RuntimeResult:
        """云端开启隔离后整个任务使用同一副本；无Docker就受控失败，不退回宿主执行。"""
        arguments = dict(project_id=project_id, context=context, run_id=run_id,
                         conversation_id=conversation_id, created_at=created_at,
                         on_text=on_text, on_tool_started=on_tool_started, on_tool_finished=on_tool_finished)
        if not (self.settings.execution_mode.lower() == "cloud" and self.settings.sandbox_enabled):
            return await self._run_agent(prompt, **arguments)
        failure = "隔离执行环境不可用或文件检查未通过；未在宿主机执行命令，已产生的合格文件尽力保留。"
        if self._sandbox_unhealthy:
            return RuntimeResult("", [], error=failure)
        if not self._sandbox_slots.acquire(blocking=False):
            return RuntimeResult("", [], error="隔离执行名额已满，请稍后重试。")
        workspace, container = None, None
        result = RuntimeResult("", [], error=failure)
        try:
            root = resolve_project_root(self.settings, project_id, repository=self.repository)
            worker = asyncio.create_task(asyncio.to_thread(SandboxWorkspace, root, WorkspaceLimits()))
            try:
                workspace = await asyncio.shield(worker)
            except asyncio.CancelledError:
                workspace = await worker
                raise
            container = ContainerExecutor(workspace, SandboxLimits(
                image=self.settings.sandbox_image, timeout_seconds=self.settings.sandbox_timeout_seconds,
                memory_mb=self.settings.sandbox_memory_mb, cpus=self.settings.sandbox_cpus,
                pids=self.settings.sandbox_pids, disk_mb=self.settings.sandbox_disk_mb,
                max_output_bytes=self.settings.sandbox_max_output_bytes))
            worker = asyncio.create_task(asyncio.to_thread(container.start))
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                await worker
                raise
            result = await self._run_agent(prompt, **arguments, sandbox_workspace=workspace,
                                           sandbox_executor=container)
        except asyncio.CancelledError:
            result.error, result.interrupted = INTERRUPTED_FAILURE, True
        except Exception as exc:
            logger.error("隔离运行失败 run_id=%s exception_type=%s", run_id, type(exc).__name__)
        finally:
            try:
                if workspace is not None:
                    # 先删除任务容器，再决定是否把任务副本写回真实项目。
                    if container is not None:
                        worker = asyncio.create_task(asyncio.to_thread(container.close))
                        try:
                            await asyncio.shield(worker)
                        except asyncio.CancelledError:
                            await worker
                            result.error, result.interrupted = INTERRUPTED_FAILURE, True
                    # 清理无法确认时不写回，不能接受仍在活动环境中的文件。
                    if container is not None and not container._unsafe:
                        worker = asyncio.create_task(asyncio.to_thread(workspace.publish))
                        try:
                            report = await asyncio.shield(worker)
                        except asyncio.CancelledError:
                            report = await worker
                            result.error, result.interrupted = INTERRUPTED_FAILURE, True
                        result.messages.append(AgentMessage(MessageType.WORKSPACE_SYNC, report))
                        if report["failed"]:
                            result.error = "部分隔离文件写回失败或存在版本冲突；请查看文件写回记录，已成功写回的文件保留。"
                            result.result = ""
                    elif container is not None:
                        self._sandbox_unhealthy = True
                        result.error = failure
            except Exception as exc:
                result.error, result.result = failure, ""
                logger.error("隔离文件收尾失败 run_id=%s exception_type=%s", run_id, type(exc).__name__)
            finally:
                if workspace is not None:
                    try:
                        workspace.close()
                    except Exception:
                        logger.error("隔离副本清理失败 run_id=%s", run_id)
                self._sandbox_slots.release()
        return result

    # 以后替换 Agent 实现时，只需要增加新的 Runtime，不用修改任务服务。
    async def _run_agent(
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
        sandbox_workspace=None,
        sandbox_executor=None,
    ) -> RuntimeResult:
        #组装Agent
        # SSE 第一步仅预留可见文字回调；后续接模型流时才调用，不能拆分最终结果假装流式。
        # 第二步已经接通：下方把 on_text 交给 Agent，再经 AgentLoop 传到模型客户端。
        # 复用应用级共享客户端（组长说明 §6.2）；没有注入时才每任务创建一次，
        # 这样测试与单脚本的行为保持不变。
        # 复用客户端最关键的一行“ 'or'左边非空就绝不构造右边；这是全部复用的关键”
        llm = self.llm_client or LLMClient(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            model=self.settings.llm_model_id,
            timeout_seconds=self.settings.llm_timeout_seconds,
        )
        project_root = sandbox_workspace.root if sandbox_workspace is not None else resolve_project_root(
            self.settings, project_id, repository=self.repository
        )
        cloud_host_test = (
            self.settings.execution_mode.lower() == "cloud"
            and self.settings.terminal_allow_cloud_host_test
        )
        local_terminal_enabled = (
            self.settings.terminal_mode == "local"
            and (self.settings.execution_mode.lower() == "local" or cloud_host_test)
        )
        registry = create_default_registry(
            project_root=project_root,
            web_api_key=self.settings.web_api_key,
            memory_repository=self.repository,
            memory_project_id=project_id,
            memory_conversation_id=conversation_id,
            memory_before_created_at=created_at,
            memory_run_id=run_id,
            sandbox_executor=sandbox_executor,
            local_terminal_enabled=local_terminal_enabled,
            local_terminal_authorizer=(lambda _request: True) if local_terminal_enabled else None,
            local_terminal_timeout_seconds=self.settings.sandbox_timeout_seconds,
            local_terminal_max_output_bytes=self.settings.sandbox_max_output_bytes,
        )
        if self.settings.execution_mode.lower() == "cloud":
            # Git 元数据只由服务端维护；文件工具不能读取/改写它（含 Windows 大小写）。
            for tool in registry.get_all():
                if tool.name in {"read_text_file", "write_text_file", "edit_text_file", "list_directory", "search_text"}:
                    tool.function = _protect_git_metadata(tool.function)
        executor = ToolExecutor(registry)
        loop = AgentLoop(llm, registry, executor)
        agent = Agent(loop)
        agent.state.max_steps = self.settings.max_agent_steps
        policy = ContextPolicy(
            model_tokens=self.settings.context_model_tokens,
            max_input_tokens=self.settings.context_max_input_tokens,
            trigger_ratio=self.settings.context_trigger_ratio,
            target_tokens=self.settings.context_target_tokens,
            max_output_tokens=self.settings.context_max_output_tokens,
            summary_tokens=self.settings.context_summary_tokens,
        )
        agent.state.context = ContextManager(llm, TokenCounter(
            llm, mode=self.settings.context_count_mode, encoding=self.settings.context_encoding,
        ), policy, run_id=run_id, recall_enabled=(conversation_id is not None
            and self.repository is not None and project_id is not None and created_at is not None))
        # 本任务内存过程绑定给现有工具；模型不能指定state或别人的项目边界。
        if conversation_id is not None and run_id is not None:
            try:
                memory_tool = registry.get("search_memory")
            except KeyError:
                pass
            else:
                memory_tool.function = partial(memory_tool.function, current_state=agent.state,
                                               current_run_id=run_id, current_prompt=prompt)

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
        agent.state.initial_history_length = len(initial_messages)
        initial_history_length = len(initial_messages)
        result, error, interrupted = "", None, False
        try:
            result = await agent.run(
                prompt, on_text=on_text,
                on_tool_started=on_tool_started, on_tool_finished=on_tool_finished,
            )
        except AgentLoopLimitError as exc:
            error = str(exc)  # 自己构造的固定说明，不是供应商错误原文。
        except ContextError as exc:
            error = str(exc)
            agent.state.status = AgentStatus.FAILED
        except asyncio.CancelledError:
            # 只暂时带回已有过程；服务层批量保存后仍重新抛出取消信号。
            error, interrupted = INTERRUPTED_FAILURE, True
            agent.state.status = AgentStatus.FAILED
        except Exception as exc:
            agent.state.status = AgentStatus.FAILED
            error = AGENT_FAILURE
            logger.error("Agent运行失败 run_id=%s step=%s exception_type=%s",
                         run_id, agent.state.step, type(exc).__name__)
        # 历史消息只帮助本轮回答，不重复保存为本轮新消息。
        return RuntimeResult(
            result=result,
            messages=(agent.state.get_history()[initial_history_length:]
                      + agent.state.context.summaries),
            error=error,
            interrupted=interrupted,
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
