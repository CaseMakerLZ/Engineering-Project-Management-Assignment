from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException, status

from .config import Settings
from .domain import Run, RunMessage
from .repository import RunRepository, create_run_repository
from .schemas import (
    CreateRunRequest,
    HealthResponse,
    RunMessagesResponse,
    RunStatusResponse,
)
from .service import RunService
from .runtime import CurrentAgentRuntime


# 创建 Python HTTP 服务，并把数据库、任务服务和 Agent 运行方式连接起来。
# 测试时可以传入假的数据库和假的 Runtime，因此不需要真的调用模型。
def create_app(
    settings: Settings | None = None,
    repository: RunRepository | None = None,
    run_service: RunService | None = None,
) -> FastAPI:
    settings = settings or Settings.from_environment()
    repository = repository or create_run_repository(settings)
    run_service = run_service or RunService(
        repository,
        # Runtime 和 RunService 共用同一个仓储，ContextBuilder 才能读取
        # 当前项目/对话的历史，并把实际上下文快照保存回同一条 agent_run。
        CurrentAgentRuntime(settings, repository),
    )

    app = FastAPI(
        title="Python Agent Service",
        version="1.0.0",
        description="Internal HTTP API consumed by the Java Spring Boot backend.",
    )
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
        run = run_service.create(request)
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

    app.include_router(router)
    app.state.settings = settings
    app.state.repository = repository
    app.state.run_service = run_service
    return app


# Uvicorn 默认导入的应用对象；测试可改用 create_app 注入隔离依赖。
app = create_app()
