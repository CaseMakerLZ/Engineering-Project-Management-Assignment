"""Java 请求的具体处理入口；创建服务和装配依赖放在 agent_service/app.py。"""

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from ..config import Settings
from ..runs.models import Run, RunMessage
from ..runs.service import RunService
from ..storage.repository import RunRepository
from ..streaming.exception import EventLimitError
from .schemas import CreateRunRequest, HealthResponse, RunMessagesResponse, RunStatusResponse


def create_router(settings: Settings, repository: RunRepository, run_service: RunService) -> APIRouter:
    """把接口连接到当前应用的配置、数据库和任务服务，不创建第二套运行对象。"""
    router = APIRouter(prefix="/api/internal")

    # 如果设置了令牌，Java 每次请求都必须带上相同的令牌，保护AgentCore的各个接口只能被java端访问。
    async def verify_token(
        x_service_token: str | None = Header(default=None),
    ) -> None:
        if settings.internal_token and x_service_token != settings.internal_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_SERVICE_TOKEN", "message": "invalid service token"},
            )

    # Java 可以用这个接口检查 Python 服务是否正常。
    @router.get("/health", response_model=HealthResponse, dependencies=[Depends(verify_token)])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service=settings.service_name)

    @router.post(
        "/runs",
        response_model=RunStatusResponse,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(verify_token)],
    )
    async def create_run(
        request: CreateRunRequest,
        background_tasks: BackgroundTasks,
    ) -> RunStatusResponse:
        # 先保存任务并立即返回 ID，耗时的 Agent 工作放到后台执行。
        try:
            run = run_service.create(request)
        except EventLimitError as exc:
            raise HTTPException(503, detail={"code": exc.code, "message": str(exc)}) from exc
        background_tasks.add_task(run_service.execute, run.run_id)
        #下面一行返回是返回给java调用端的
        return RunStatusResponse(run_id=run.run_id, status=run.status)

    @router.get(
        "/runs/{run_id}",
        response_model=Run,
        response_model_exclude={"context"},
        dependencies=[Depends(verify_token)],
    )
    async def get_run(run_id: str) -> Run:
        # 这里只读取任务状态，不会重新执行 Agent。
        run = repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @router.get("/runs/{run_id}/events", dependencies=[Depends(verify_token)])
    async def get_events(run_id: str) -> StreamingResponse:
        """仅订阅现有运行；读库一次，不循环查状态，也不在流中持有数据库连接。"""
        try:
            run = await run_in_threadpool(repository.get_run, run_id)
        except Exception as exc:
            raise HTTPException(503, detail={
                "code": "STORAGE_UNAVAILABLE", "message": "任务存储暂不可用"
            }) from exc
        if run is None:
            raise HTTPException(404, detail="run not found")
        try:
            subscription = run_service.events.subscribe(run)
        except EventLimitError as exc:
            raise HTTPException(
                429 if exc.code == "SUBSCRIPTION_LIMIT" else 503,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        # 订阅的 finally 不调用 execute/cancel，连接断开不会中断后台任务。
        return StreamingResponse(subscription.frames(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
        })

    @router.get(
        "/runs/{run_id}/messages",
        response_model=RunMessagesResponse,
        dependencies=[Depends(verify_token)],
    )
    async def get_messages(run_id: str) -> RunMessagesResponse:
        # 过程消息单独查询，任务详情只返回任务状态和最终结果。
        if repository.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        messages = repository.list_messages(run_id)
        return RunMessagesResponse(
            run_id=run_id,
            messages=[RunMessage.model_validate(message) for message in messages],
        )

    @router.post(
        "/runs/{run_id}/cancel",
        response_model=RunStatusResponse,
        dependencies=[Depends(verify_token)],
    )
    async def cancel_run(run_id: str) -> RunStatusResponse:
        # 当前取消会改变任务状态，但不会强行中断已经发出的模型请求。
        run = run_service.cancel(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return RunStatusResponse(run_id=run.run_id, status=run.status)

    return router
