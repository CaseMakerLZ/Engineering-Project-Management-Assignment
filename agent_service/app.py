from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings
from .http.routes import create_router
from .runs.runtime import CurrentAgentRuntime
from .runs.service import RunService
from .storage.repository import RunRepository, create_run_repository


# 创建 Python HTTP 服务，并把数据库、任务服务和 Agent 运行方式连接起来。
# 测试时可以传入假的数据库和假的 Runtime，因此不需要真的调用模型。
def create_app(
    settings: Settings | None = None,
    repository: RunRepository | None = None,
    run_service: RunService | None = None,
) -> FastAPI:
    settings = settings or Settings.from_environment()
    if settings.execution_mode.lower() == "cloud" and not (
        settings.internal_token and settings.internal_token.strip()
    ):
        raise ValueError("cloud 模式必须配置非空内部服务令牌")
    if repository is None and run_service is not None:
        repository = run_service.repository
    repository = repository or create_run_repository(settings)
    run_service = run_service or RunService(
        repository,
        # Runtime 和 RunService 共用同一个仓储，ContextBuilder 才能读取
        # 当前项目/对话的历史，并把实际上下文快照保存回同一条 agent_run。
        CurrentAgentRuntime(settings, repository),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            run_service.events.close()

    app = FastAPI(
        title="Python Agent Service",
        version="1.0.0",
        description="Internal HTTP API consumed by the Java Spring Boot backend.",
        lifespan=lifespan,
    )
    app.include_router(create_router(settings, repository, run_service))
    app.state.settings = settings
    app.state.repository = repository
    app.state.run_service = run_service
    return app


# Uvicorn 默认导入的应用对象；测试可改用 create_app 注入隔离依赖。
app = create_app()
