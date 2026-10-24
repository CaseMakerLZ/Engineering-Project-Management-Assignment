from datetime import datetime, timezone
from uuid import uuid4

from .domain import Run, RunStatus
from .repository import RunRepository
from .runtime import AgentRuntime
from .schemas import CreateRunRequest


def _now() -> datetime:
    """返回当前的 UTC 时间。"""
    return datetime.now(timezone.utc)


class RunService:
    """创建、执行、查询和取消 Agent 运行。"""
    def __init__(
        self,
        repository: RunRepository,
        runtime: AgentRuntime,
    ) -> None:
        self.repository = repository
        self.runtime = runtime

    def create(self, request: CreateRunRequest) -> Run:
        run = Run(
            run_id=str(uuid4()),
            project_id=request.project_id,
            conversation_id=request.conversation_id,
            prompt=request.prompt,
            context=[message.model_dump() for message in request.context],
            status=RunStatus.CREATED,
            result=None,
            error=None,
            created_at=_now(),
        )
        return self.repository.create_run(run)
    # 后台执行一项已经创建的 Agent 任务。
    async def execute(self, run_id: str) -> None:
        # 找到要执行的任务。
        run = self.repository.get_run(run_id)
        # 任务不存在或已经开始执行时，不重复执行。
        if run is None or run.status != RunStatus.CREATED:
            return
        # 记录任务开始执行。
        run.status = RunStatus.RUNNING
        run.started_at = _now()
        self.repository.update_run(run)

        try:
            # 调用 Agent Core 得到回答和过程消息。
            runtime_result = await self.runtime.run(
                run.prompt,
                project_id=run.project_id,
                context=run.context,
                run_id=run.run_id,
                conversation_id=run.conversation_id,
                created_at=run.created_at,
            )
            latest_run = self.repository.get_run(run_id)
            if latest_run is None or latest_run.status == RunStatus.CANCELLED:
                return
            run = latest_run
            self.repository.append_messages(
                run_id,
                [(message.type.value, message.content) for message in runtime_result.messages],
            )
            run.status = RunStatus.COMPLETED
            run.result = runtime_result.result
        except Exception as exc:
            latest_run = self.repository.get_run(run_id)
            if latest_run is not None and latest_run.status == RunStatus.CANCELLED:
                return
            run.status = RunStatus.FAILED
            run.error = str(exc)
        finally:
            latest_run = self.repository.get_run(run_id)
            if latest_run is not None and latest_run.status == RunStatus.CANCELLED:
                return
            run.finished_at = _now()
            self.repository.update_run(run)

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
        return self.repository.update_run(run)
