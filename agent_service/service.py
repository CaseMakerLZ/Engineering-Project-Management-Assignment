from datetime import datetime, timezone
from uuid import uuid4

from .domain import RunRecord, RunStatus
from .repository import SQLiteRunRepository
from .runtime import AgentRuntime, serialize_message
from .schemas import CreateRunRequest


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RunService:
    def __init__(
        self,
        repository: SQLiteRunRepository,
        runtime: AgentRuntime,
    ) -> None:
        self.repository = repository
        self.runtime = runtime

    def create(self, request: CreateRunRequest) -> RunRecord:
        run = RunRecord(
            run_id=str(uuid4()),
            project_id=request.project_id,
            prompt=request.prompt,
            status=RunStatus.CREATED,
            result=None,
            error=None,
            created_at=_now(),
        )
        return self.repository.create_run(run)
    #异步执行 Agent 任务，是整个服务最重要的函数。
    async def execute(self, run_id: str) -> None:
        # 1. 根据 run_id 找到任务RunRecord对象
        run = self.repository.get_run(run_id)
        # 2. 如果任务不存在，或者已经不是 CREATED，就不执行
        if run is None or run.status != RunStatus.CREATED:
            return
        # 3. 标记任务开始运行
        run.status = RunStatus.RUNNING
        run.started_at = _now()
        self.repository.update_run(run)

        try:
            # 4. 真正调用 Agent Core
            runtime_result = await self.runtime.run(run.prompt, run.project_id)
            latest_run = self.repository.get_run(run_id)
            if latest_run is None or latest_run.status == RunStatus.CANCELLED:
                return
            run = latest_run
            self.repository.append_messages(
                run_id,
                [serialize_message(message) for message in runtime_result.messages],
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

    def cancel(self, run_id: str) -> RunRecord | None:
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
