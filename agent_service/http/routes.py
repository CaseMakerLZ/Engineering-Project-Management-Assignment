"""Java 请求的具体处理入口；创建服务和装配依赖放在 agent_service/app.py。"""

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from ..config import Settings
from ..runs.models import Run, RunMessage
from ..runs.service import RunService
from ..storage.repository import RunRepository
from ..streaming.exception import EventLimitError
from ..workspace.exception import WorkspaceError, WorkspaceErrorCode
from ..workspace.service import WorkspaceService
from .schemas import CreateRunRequest, HealthResponse, RunMessagesResponse, RunStatusResponse


# 工作区错误码到 HTTP 状态码的翻译表，对应 Java 说明第 6.5 节。
# Python 只表达真实失败原因，Java 再按 code 翻译成业务码，双方都不解析异常文本。
# 413 用字面值：不同 starlette 版本对 HTTP_413_* 常量的命名不一致。
_HTTP_STATUS_BY_WORKSPACE_CODE = {
    WorkspaceErrorCode.INVALID_PATH.value: status.HTTP_400_BAD_REQUEST,
    WorkspaceErrorCode.PROJECT_NOT_FOUND.value: status.HTTP_404_NOT_FOUND,
    WorkspaceErrorCode.ENTRY_NOT_FOUND.value: status.HTTP_404_NOT_FOUND,
    WorkspaceErrorCode.PATH_FORBIDDEN.value: status.HTTP_404_NOT_FOUND,
    WorkspaceErrorCode.PROJECT_BUSY.value: status.HTTP_409_CONFLICT,
    WorkspaceErrorCode.CURSOR_EXPIRED.value: status.HTTP_409_CONFLICT,
    WorkspaceErrorCode.PREVIEW_TOO_LARGE.value: 413,
    WorkspaceErrorCode.DOWNLOAD_TOO_LARGE.value: 413,
    WorkspaceErrorCode.ARCHIVE_TOO_LARGE.value: 413,
    WorkspaceErrorCode.DIRECTORY_TOO_LARGE.value: 413,
    WorkspaceErrorCode.PROJECT_QUOTA_EXCEEDED.value: 413,
    WorkspaceErrorCode.PREVIEW_UNSUPPORTED.value: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    WorkspaceErrorCode.WORKSPACE_UNAVAILABLE.value: status.HTTP_503_SERVICE_UNAVAILABLE,
    WorkspaceErrorCode.GIT_UNAVAILABLE.value: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _workspace_http_error(exc: WorkspaceError) -> HTTPException:
    """把工作区域异常翻译成只含 code/message 的 HTTP 错误。

    未知错误码统一按服务不可用处理，不把异常原文、路径或底层驱动错误送到页面。
    """
    return HTTPException(
        status_code=_HTTP_STATUS_BY_WORKSPACE_CODE.get(
            exc.code, status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        detail={"code": exc.code, "message": exc.public_message()},
    )


def create_router(
    settings: Settings,
    repository: RunRepository,
    run_service: RunService,
    workspace_service: WorkspaceService,
) -> APIRouter:
    """把接口连接到当前应用的配置、数据库和任务服务，不创建第二套运行对象。"""
    router = APIRouter(prefix="/api/internal")

    # 如果设置了令牌，Java 每次请求都必须带上相同的令牌，保护AgentCore的各个接口只能被java端访问。
    async def verify_token(
        x_service_token: str | None = Header(default=None),
    ) -> None:
        """校验内部服务令牌；配置了令牌时，请求头必须与之一致，否则 401。"""

        if settings.internal_token and x_service_token != settings.internal_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_SERVICE_TOKEN", "message": "invalid service token"},
            )

    # Java 可以用这个接口检查 Python 服务是否正常。
    @router.get("/health", response_model=HealthResponse, dependencies=[Depends(verify_token)])
    async def health() -> HealthResponse:
        """健康检查：只回服务名与 ok，不查库、不执行任务。"""

        return HealthResponse(status="ok", service=settings.service_name)

    # 项目提交后准备云端目录。重复调用只补缺失目录，不清空文件、不重建 Git。
    # 放在任务接口之前，贴合 Java 的实际调用顺序：建项目 → 准备目录 → 提交任务。
    @router.put("/projects/{project_id}/workspace", dependencies=[Depends(verify_token)])
    async def prepare_project_workspace(project_id: str) -> dict:
        """准备云端项目目录，返回 ``{project_id, ready}``；重复调用只补缺失目录。"""

        try:
            # mkdir 与归属查询都是阻塞调用，不能占住事件循环。
            prepared = await run_in_threadpool(workspace_service.prepare_project, project_id)
        except WorkspaceError as exc:
            raise _workspace_http_error(exc) from exc
        return prepared.to_dict()

    # 目录树：只返回当前目录的直接子项（Java 说明 §6.1、组长说明 §4.1）。
    # 目录在前、名称稳定排序；next_cursor 非空表示还有下一页。
    @router.get("/projects/{project_id}/files/tree", dependencies=[Depends(verify_token)])
    async def list_project_directory(
        project_id: str,
        path: str = "",
        page_size: int | None = None,
        cursor: str | None = None,
    ) -> dict:
        """读取一个目录的直接子项，返回 Java 说明 §6.1 的 data 本体。

        ``path`` 空串表示项目根；``next_cursor`` 非空表示还有下一页；
        目录在分页期间变化时返回 409（CURSOR_EXPIRED），要求重读第一页。
        """

        try:
            # 目录枚举是阻塞 IO，放进线程池，避免占住事件循环。
            page = await run_in_threadpool(
                workspace_service.list_directory, project_id, path, page_size, cursor
            )
        except WorkspaceError as exc:
            raise _workspace_http_error(exc) from exc
        return page.to_dict()

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
        """创建任务并立刻返回 ID，Agent 在后台执行；容量满时 503 受控拒绝。"""

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
        """读取任务状态与最终结果（不含上下文快照）；不存在返回 404，不重新执行。"""

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
        """读取一次运行的过程消息；任务详情只返回状态和最终结果，过程消息单独查。"""

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
        """把任务标记为 CANCELLED；不强行中断已经发出的模型请求。"""

        # 当前取消会改变任务状态，但不会强行中断已经发出的模型请求。
        run = run_service.cancel(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return RunStatusResponse(run_id=run.run_id, status=run.status)

    return router
