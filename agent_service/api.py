from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException, status

from .config import Settings
from .domain import RunStatus
from .repository import SQLiteRunRepository
from .schemas import (
    CancelRunResponse,
    CreateRunRequest,
    CreateRunResponse,
    ErrorResponse,
    HealthResponse,
    MessageResponse,
    RunMessagesResponse,
    RunResponse,
)
from .service import RunService
from .runtime import CurrentAgentRuntime


def create_app(
    settings: Settings | None = None,
    repository: SQLiteRunRepository | None = None,
    run_service: RunService | None = None,
) -> FastAPI:
    settings = settings or Settings.from_environment()
    repository = repository or SQLiteRunRepository(settings.database_path)
    run_service = run_service or RunService(repository, CurrentAgentRuntime())

    app = FastAPI(
        title="Python Agent Service",
        version="1.0.0",
        description="Internal HTTP API consumed by the Java Spring Boot backend.",
    )
    router = APIRouter(prefix="/api/internal")

    async def verify_token(
        x_service_token: str | None = Header(default=None),
    ) -> None:
        if settings.internal_token and x_service_token != settings.internal_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_SERVICE_TOKEN", "message": "invalid service token"},
            )

    @router.get("/health", response_model=HealthResponse, dependencies=[Depends(verify_token)])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service=settings.service_name)

    @router.post(
        "/runs",
        response_model=CreateRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(verify_token)],
    )
    async def create_run(
        request: CreateRunRequest,
        background_tasks: BackgroundTasks,
    ) -> CreateRunResponse:
        run = run_service.create(request)
        background_tasks.add_task(run_service.execute, run.run_id)
        return CreateRunResponse(run_id=run.run_id, status=run.status)

    @router.get(
        "/runs/{run_id}",
        response_model=RunResponse,
        dependencies=[Depends(verify_token)],
    )
    async def get_run(run_id: str) -> RunResponse:
        run = repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return RunResponse.model_validate(run, from_attributes=True)

    @router.get(
        "/runs/{run_id}/messages",
        response_model=RunMessagesResponse,
        dependencies=[Depends(verify_token)],
    )
    async def get_messages(run_id: str) -> RunMessagesResponse:
        if repository.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        messages = repository.list_messages(run_id)
        return RunMessagesResponse(
            run_id=run_id,
            messages=[MessageResponse.model_validate(message, from_attributes=True) for message in messages],
        )

    @router.post(
        "/runs/{run_id}/cancel",
        response_model=CancelRunResponse,
        dependencies=[Depends(verify_token)],
    )
    async def cancel_run(run_id: str) -> CancelRunResponse:
        run = run_service.cancel(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return CancelRunResponse(run_id=run.run_id, status=run.status)

    app.include_router(router)
    app.state.settings = settings
    app.state.repository = repository
    app.state.run_service = run_service
    return app


app = create_app()

