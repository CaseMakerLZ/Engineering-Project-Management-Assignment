from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .http.routes import create_router
from .runs.runtime import CurrentAgentRuntime
from .runs.service import RunService
from .storage.repository import RunRepository, create_run_repository
from .storage.mysql_pool import MySQLPoolError
from .workspace.service import WorkspaceService
from llm.client import LLMClient


# 创建 Python HTTP 服务，并把数据库、任务服务和 Agent 运行方式连接起来。
# 测试时可以传入假的数据库和假的 Runtime，因此不需要真的调用模型。
def create_app(
    settings: Settings | None = None,
    repository: RunRepository | None = None,
    run_service: RunService | None = None,
) -> FastAPI:
    """创建 Python HTTP 服务，并把仓储、任务服务、工作区服务和 Agent 运行方式连起来。

    测试可以注入假仓储和假 Runtime，因此不需要真的调用模型或连接数据库；
    cloud 模式必须配置非空内部服务令牌，否则拒绝启动。
    """

    settings = settings or Settings.from_environment()
    if settings.execution_mode.lower() == "cloud" and not (
        settings.internal_token and settings.internal_token.strip()
    ):
        raise ValueError("cloud 模式必须配置非空内部服务令牌")
    if repository is None and run_service is not None:
        repository = run_service.repository
    # 应用只关闭自己创建的仓储；外部注入的仓储由调用方管理。
    owns_repository = repository is None
    repository = repository or create_run_repository(settings)
    # 模型客户端由应用创建一次并共享（组长说明 §6.2）：不每任务重建，关闭时释放。
    # 只在配置了凭据时创建；测试与无凭据环境保持原行为（运行期才创建）。
    shared_llm = None
    if run_service is None and settings.llm_api_key:
        shared_llm = LLMClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model_id,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    run_service = run_service or RunService(
        repository,
        # Runtime 和 RunService 共用同一个仓储，ContextBuilder 才能读取
        # 当前项目/对话的历史，并把实际上下文快照保存回同一条 agent_run。
        CurrentAgentRuntime(settings, repository, llm_client=shared_llm),
        max_concurrent_runs=settings.max_concurrent_runs,
    )
    # 工作区准备与任务运行共用同一个仓储：项目归属只有一份可信来源。
    workspace_service = WorkspaceService(settings, repository)
    run_service.workspace = workspace_service

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """应用关闭时释放 SSE 订阅、共享模型客户端；
        不取消进行中的 Agent:应用关闭时，可能有 Agent 任务正在跑。这段代码没有主动取消它们，只关闭底层资源（事件广播、LLM 客户端）。
        """
        '''
        这是 FastAPI 的生命周期钩子。
        FastAPI 启动时调用这个函数，执行到 yield 时暂停，把控制权交还给 FastAPI——此时应用开始对外服务。
        应用关闭时，从 yield 处恢复，执行 finally 里的清理代码。
        '''
        try:
            yield
        finally:
            run_service.events.close()
            try:
                if shared_llm is not None:
                    await shared_llm.close()
            finally:
                if owns_repository:
                    repository.close()

    app = FastAPI(
        title="Python Agent Service",
        version="1.0.0",
        description="Internal HTTP API consumed by the Java Spring Boot backend.",
        lifespan=lifespan,
    )

    @app.exception_handler(MySQLPoolError)
    async def mysql_pool_unavailable(request: Request, exc: MySQLPoolError) -> JSONResponse:
        """连接借满时明确告知暂不可用，不把内部异常当成正常查询结果。"""
        return JSONResponse(status_code=503, content={
            "detail": {"code": exc.code, "message": str(exc)},
        })

    app.include_router(create_router(settings, repository, run_service, workspace_service))
    app.state.settings = settings
    app.state.repository = repository
    app.state.run_service = run_service
    app.state.workspace_service = workspace_service
    return app


# Uvicorn 默认导入的应用对象；测试可改用 create_app 注入隔离依赖。
app = create_app()
