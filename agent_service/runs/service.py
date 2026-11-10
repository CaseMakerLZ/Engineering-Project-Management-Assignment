import asyncio
import threading
import logging
from datetime import datetime, timezone
from uuid import uuid4

from .models import Run, RunStatus
from ..storage.repository import RunRepository
from .runtime import AgentRuntime
from ..http.schemas import CreateRunRequest
from agent.message import AgentMessage, MessageType
from agent.exception import AGENT_FAILURE, INTERRUPTED_FAILURE
from llm.mapper import reasoning_display_content
from ..streaming.service import RunEvents
from tools.executor import ToolExecutionResult
from ..workspace.service import WorkspaceService
from ..workspace.exception import WorkspaceError, WorkspaceErrorCode
from tools.filesystem.FileToolExecutionOutput import WriteFileOutput, EditFileOutput

logger = logging.getLogger(__name__)

class RunCapacityError(RuntimeError):
    """当前进程的 Agent 执行名额已用完；调用方应稍后重试。"""

    code = "RUN_CAPACITY_EXCEEDED"


def _now() -> datetime:
    """返回当前的 UTC 时间。"""
    return datetime.now(timezone.utc)


class RunService:
    """创建、执行、查询和取消 Agent 运行。"""
    def __init__(
        self,
        repository: RunRepository,
        runtime: AgentRuntime,
        events: RunEvents | None = None,
        workspace: WorkspaceService | None = None,
        max_concurrent_runs: int | None = None,
    ) -> None:
        self.repository = repository
        self.runtime = runtime
        self.events = events or RunEvents()
        # 同一应用进程内防止 await 数据库时重复启动；不是跨进程的任务锁。
        self._executing: set[str] = set()
        self.workspace = workspace
        self._project_leases: dict[str, object] = {}
        configured_limit = max_concurrent_runs
        if configured_limit is None:
            configured_limit = getattr(getattr(runtime, "settings", None), "max_concurrent_runs", 4)
        self._run_slots = threading.BoundedSemaphore(max(1, int(configured_limit)))
        self._run_slot_lock = threading.Lock()
        self._run_slot_holders: set[str] = set()

    def create(self, request: CreateRunRequest) -> Run:
        run = Run(
            run_id=str(uuid4()),
            project_id=request.project_id,
            conversation_id=request.conversation_id,
            prompt=request.prompt,
            # context 字段仅保留 HTTP 兼容性；运行前的实际快照由 Python 组装后写入。
            # 若组装前失败，也不能把请求里未使用的历史误记为模型上下文。
            context=[],
            status=RunStatus.CREATED,
            result=None,
            error=None,
            created_at=_now(),
        )
        if not self._run_slots.acquire(blocking=False):
            #_run_slots是信号量对象，acquire表示信号量减1（wait操作），blocking=False表示信号量减为0时不阻塞直接返回False
            #含义是信号量减为0时（即到达设置能进入缓冲区上限时）直接抛出以下异常
            raise RunCapacityError("Agent 当前正在处理较多任务，请稍后重试")
        #若通过了上面的判断，则
        with self._run_slot_lock:
            self._run_slot_holders.add(run.run_id)
        slot_acquired = True
        lease = None
        try:
            if self.workspace is not None and self.workspace.settings.execution_mode.lower() == "cloud":
                if not run.project_id:
                    raise WorkspaceError(WorkspaceErrorCode.INVALID_PATH, "云端任务必须指定项目")
                lease = self.workspace.usage.acquire(run.project_id, "agent")
                if lease is None:
                    raise WorkspaceError(WorkspaceErrorCode.PROJECT_BUSY, "项目正在运行或打包")
            self.events.register(run.run_id)
            saved = self.repository.create_run(run)
            if lease is not None:
                self._project_leases[run.run_id] = lease
            return saved
        except BaseException:
            self.events.discard(run.run_id)
            if slot_acquired:
                self._release_run_slot(run.run_id)
            if lease is not None:
                self.workspace.usage.release(lease)
            raise
    # 后台执行一项已经创建的 Agent 任务。
    async def execute(self, run_id: str) -> None:
        if run_id in self._executing:
            return
        self._executing.add(run_id)
        try:
            await self._execute(run_id)
        except asyncio.CancelledError:
            # _execute 已按运行中断保存 FAILED；不要把正常收尾误称为存储故障。
            raise
        except BaseException:
            # 写库/协程中断不能发 completed，通道应明确结束而非永久显示 RUNNING。
            self.events.storage_failed(run_id)
            raise
        finally:
            self._executing.discard(run_id)
            lease = self._project_leases.pop(run_id, None)
            if lease is not None:
                self.workspace.usage.release(lease)
            self._release_run_slot(run_id)

    def _release_run_slot(self, run_id: str) -> None:
        """归还任务名额；重复归还不会增加可用名额。"""
        with self._run_slot_lock:
            if run_id not in self._run_slot_holders:
                return
            self._run_slot_holders.remove(run_id)
        self._run_slots.release()

    async def _execute(self, run_id: str) -> None:
        """事件只通知已经保存的状态；数据库错误仍向上抛出供服务端诊断。"""
        # 找到要执行的任务。
        run = self.repository.get_run(run_id)
        # 任务不存在或已经开始执行时，不重复执行。
        if run is None or run.status != RunStatus.CREATED:
            return
        self.events.register(run_id)
        # 记录任务开始执行。
        run.status = RunStatus.RUNNING
        run.started_at = _now()
        self.repository.update_run(run)
        self.events.started(run_id)

        runtime_result = None
        stored_messages = []
        try:
            written_paths: list[str] = []
            version_saved = True
            # 调用 Agent Core 得到回答和过程消息。
            def receive_text(message_id: str, text: str) -> None:
                self.events.text(run_id, message_id, text)

            def tool_started(call_id: str, tool_name: str) -> None:
                self.events.tool_started(run_id, call_id, tool_name)

            def tool_finished(call_id: str, tool_name: str, result: ToolExecutionResult) -> None:
                # 原始错误和工具输出不交给页面；发送模块只接收成功标志与错误码。
                self.events.tool_finished(run_id, call_id, tool_name, result.success, result.error_code)
                if result.success and tool_name in {"write_text_file", "edit_text_file"}:
                    output = result.output
                    if isinstance(output, (WriteFileOutput, EditFileOutput)):
                        output = output.model_dump()
                    if isinstance(output, dict) and isinstance(output.get("path"), str):
                        if len(written_paths) < 200:
                            written_paths.append(output["path"])

            runtime_result = await self.runtime.run(
                run.prompt,
                project_id=run.project_id,
                run_id=run.run_id,
                conversation_id=run.conversation_id,
                created_at=run.created_at,
                on_text=receive_text,
                on_tool_started=tool_started,
                on_tool_finished=tool_finished,
            )
            latest_run = self.repository.get_run(run_id)
            if latest_run is None or latest_run.status == RunStatus.CANCELLED:
                return
            run = latest_run
            if runtime_result.interrupted:
                raise asyncio.CancelledError()
            if runtime_result.error is not None:
                run.status = RunStatus.FAILED
                run.result = None
                run.error = runtime_result.error
                return
            if len(runtime_result.result.encode("utf-8")) > self.events.max_text_bytes:
                raise ValueError("运行最终回答超过可见输出上限")
            if self.workspace is not None and self.workspace.settings.execution_mode.lower() == "cloud":
                # Git 是同步磁盘工作；协程取消也等待实际线程退出，才释放项目名额。
                worker = asyncio.create_task(asyncio.to_thread(
                    self.workspace.finish_run, run.project_id, run_id,
                    runtime_result.result, written_paths, self.events.max_text_bytes,
                ))
                try:
                    result, version_saved = await asyncio.shield(worker)
                except asyncio.CancelledError:
                    await asyncio.shield(worker)
                    raise
                runtime_result.result = result
                # 等待 Git 时可能收到取消请求，不能覆盖其状态。
                latest_run = self.repository.get_run(run_id)
                if latest_run is None or latest_run.status == RunStatus.CANCELLED:
                    return
                if not version_saved:
                    self.events.warning(run_id, "VERSION_SAVE_FAILED", "文件已更新，但本次版本记录未保存")
                    # 告警已进入最终 result，刷新后仍可见，不伪造一条模型历史消息。
            # 与流的总可见输出限制一致；先校验再保存 completed。
            if len(runtime_result.result.encode("utf-8")) > self.events.max_text_bytes:
                raise ValueError("运行最终回答超过可见输出上限")
            if not version_saved:
                stored_messages.append(("warning", {"code": "VERSION_SAVE_FAILED",
                    "message": "文件已更新，但本次版本记录未保存"}))
            run.status = RunStatus.COMPLETED
            run.result = runtime_result.result
        except asyncio.CancelledError:
            # 应用关闭导致的协程中断不能被保存成 COMPLETED；不是页面断线取消。
            run.status = RunStatus.FAILED
            run.result = None
            run.error = INTERRUPTED_FAILURE
            raise
        except Exception as exc:
            latest_run = self.repository.get_run(run_id)
            if latest_run is not None and latest_run.status == RunStatus.CANCELLED:
                return
            run.status = RunStatus.FAILED
            run.result = None
            run.error = AGENT_FAILURE
            logger.error("任务执行失败 run_id=%s exception_type=%s", run_id, type(exc).__name__)
        finally:
            # 正常完成和异常返回共用一个批量保存点；不逐段写，不重试整批写入。
            try:
                if runtime_result is not None:
                    stored_messages = [
                        _message_for_storage(message) for message in runtime_result.messages
                    ] + stored_messages
                self.repository.append_messages(run_id, stored_messages)
            except Exception:
                logger.error("过程保存失败 run_id=%s execution_error=%s", run_id, run.error)
                # 能写状态时尽力留下 FAILED；保留先前执行原因，不覆盖成保存错误。
                try:
                    latest_run = self.repository.get_run(run_id)
                    if latest_run is not None and latest_run.status != RunStatus.CANCELLED:
                        run.status = RunStatus.FAILED
                        run.result = None
                        run.error = run.error or "运行过程保存失败，请检查服务端日志；已产生的文件保留。"
                        run.finished_at = _now()
                        self.repository.update_run(run)
                except Exception:
                    logger.error("过程保存失败后，终态也无法保存 run_id=%s", run_id)
                # 外层 execute 会发存储失败通知，不能继续发完成通知。
                raise
            latest_run = self.repository.get_run(run_id)
            if latest_run is not None and latest_run.status == RunStatus.CANCELLED:
                return
            run.finished_at = _now()
            self.repository.update_run(run)
            self.events.finished(run)

    def cancel(self, run_id: str) -> Run | None:
        run = self.repository.get_run(run_id)
        if run is None or run.status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            return run
        run.status = RunStatus.CANCELLED
        run.finished_at = _now()
        saved = self.repository.update_run(run)
        self.events.finished(saved)
        return saved


def _message_for_storage(message: AgentMessage) -> tuple[str, object]:
    """reasoning 同时保存原始项与可读文本，其余消息保持原有格式。"""
    if message.type != MessageType.REASONING:
        return message.type.value, message.content

    readable_text, display_type = reasoning_display_content(message.content)
    return message.type.value, {
        "provider_item": message.content,
        "display_text": readable_text,
        "display_type": display_type,
    }
