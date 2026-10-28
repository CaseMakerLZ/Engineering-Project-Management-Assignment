import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from .models import Run, RunStatus
from ..storage.repository import RunRepository
from .runtime import AgentRuntime
from ..http.schemas import CreateRunRequest
from agent.message import AgentMessage, MessageType
from llm.mapper import reasoning_display_content
from ..streaming.service import RunEvents


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
    ) -> None:
        self.repository = repository
        self.runtime = runtime
        self.events = events or RunEvents()
        # 同一应用进程内防止 await 数据库时重复启动；不是跨进程的任务锁。
        self._executing: set[str] = set()

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
        self.events.register(run.run_id)
        try:
            return self.repository.create_run(run)
        except Exception:
            self.events.discard(run.run_id)
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

        try:
            # 调用 Agent Core 得到回答和过程消息。
            runtime_result = await self.runtime.run(
                run.prompt,
                project_id=run.project_id,
                run_id=run.run_id,
                conversation_id=run.conversation_id,
                created_at=run.created_at,
                on_text=lambda message_id, delta: self.events.text(run_id, message_id, delta),
            )
            latest_run = self.repository.get_run(run_id)
            if latest_run is None or latest_run.status == RunStatus.CANCELLED:
                return
            run = latest_run
            # 与流的总可见输出限制一致；先校验再保存 completed。
            if len(runtime_result.result.encode("utf-8")) > self.events.max_text_bytes:
                raise ValueError("运行最终回答超过可见输出上限")
            self.repository.append_messages(
                run_id,
                [_message_for_storage(message) for message in runtime_result.messages],
            )
            run.status = RunStatus.COMPLETED
            run.result = runtime_result.result
        except asyncio.CancelledError:
            # 应用关闭导致的协程中断不能被保存成 COMPLETED；不是页面断线取消。
            run.status = RunStatus.FAILED
            run.result = None
            run.error = "运行协程被中断"
            raise
        except Exception as exc:
            latest_run = self.repository.get_run(run_id)
            if latest_run is not None and latest_run.status == RunStatus.CANCELLED:
                return
            run.status = RunStatus.FAILED
            run.result = None
            run.error = str(exc)
        finally:
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
