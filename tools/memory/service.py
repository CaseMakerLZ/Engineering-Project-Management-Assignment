"""search_memory 的历史回溯与结果裁剪，以及 remember 的项目长期记忆写入。"""

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from agent_service.runs.models import Run
from agent_service.storage.repository import MemoryRepository

from .RememberToolExecutionOutput import RememberOutput
from .SearchMemoryToolExecutionOutput import (
    MemoryProcessMessage,
    MemoryRunResult,
    SearchMemoryOutput,
)
from .exception import MemoryErrorCode, MemoryToolError
from .params import RememberArgs, SearchMemoryArgs


_MAX_CANDIDATE_RUNS = 1000
_MAX_PROCESS_MESSAGES = 100
_MAX_CONTENT_CHARS = 4_000


def search_memory(
    *,
    match_text: str | None = None,
    fuzzy_match: bool = False,
    time_range: dict[str, Any] | None = None,
    limit: int = 5,
    include_process: bool = False,
    repository: MemoryRepository,
    project_id: str,
    conversation_id: str | None,
    before_created_at: datetime,
) -> SearchMemoryOutput:
    """在当前项目、当前对话内查询历史运行。

    ``project_id``、``conversation_id`` 和 ``before_created_at`` 都由运行时绑定；
    它们不是模型参数。普通查询只读取 agent_run（当前上下问组装也直接使用agent_run）。
    过程回溯才读取 agent_run_message，而agent的reasoning也放在agent_run_message里面意味着有需要时可以进行当时思路的回溯
    """
    if conversation_id is None:
        raise MemoryToolError(
            MemoryErrorCode.CONFIGURATION_ERROR,
            "当前运行没有 conversation_id，不能进行对话范围内的记忆检索",
        )
    if not 1 <= limit <= 10:
        raise MemoryToolError(MemoryErrorCode.INVALID_ARGUMENT, "limit 必须在 1 到 10 之间")

    validated_args = SearchMemoryArgs(
        match_text=match_text,
        fuzzy_match=fuzzy_match,
        time_range=time_range or {},
        limit=limit,
        include_process=include_process,
    )
    match_text = validated_args.match_text
    fuzzy_match = validated_args.fuzzy_match
    limit = validated_args.limit
    include_process = validated_args.include_process
    parsed_range = validated_args.time_range
    before = _as_utc(before_created_at)
    end = _as_utc(parsed_range.end) if parsed_range.end is not None else before
    end = min(end, before)
    start = (
        _as_utc(parsed_range.start)
        if parsed_range.start is not None
        else end - timedelta(days=7)
    )
    if start > end:
        raise MemoryToolError(MemoryErrorCode.INVALID_ARGUMENT, "时间范围起点不能晚于终点")

    # 多取一条用于判断是否还有结果，但最终仍只向模型返回 limit 条。
    candidate_limit = (
        _MAX_CANDIDATE_RUNS + 1
        if fuzzy_match and match_text
        else limit + 1
    )
    try:
        runs = repository.list_memory_runs(
            project_id,
            conversation_id,
            before,
            start,
            end,
            candidate_limit,
        )
    except MemoryToolError:
        raise
    except Exception as exc:
        raise MemoryToolError(
            MemoryErrorCode.STORAGE_ERROR,
            "读取历史运行失败",
            cause=exc,
        ) from exc

    normalized_match = match_text.casefold() if fuzzy_match and match_text else None
    matched = [
        run
        for run in runs
        if normalized_match is None
        or normalized_match in _search_text(run).casefold()
    ]
    # 仓储按时间正序返回，回忆结果按最新运行优先返回。
    selected = list(reversed(matched))[:limit]
    truncated = len(matched) > limit or (
        len(runs) > _MAX_CANDIDATE_RUNS and normalized_match is not None
    )

    results = [
        _to_result(run, repository, include_process=include_process)
        for run in selected
    ]
    return SearchMemoryOutput(
        results=results,
        returned_count=len(results),
        has_more=truncated,
        truncated=truncated,
    )


def remember(
    *,
    memory_id: str | None = None,
    content: str,
    repository: MemoryRepository,
    project_id: str,
    source_run_id: str,
) -> RememberOutput:
    """保存当前运行明确提出的一条长期记忆。

    项目和来源运行由服务端绑定；模型只提交内容，以及更新时需要的已有 ID。
    不传 ID 就新建，传 ID 只能原地更新同项目记忆，不创建替代记录或版本链。
    该函数不会调用 LLM，也不会从整段历史中自动提取内容。
    """
    try:
        validated_args = RememberArgs(
            memory_id=memory_id,
            content=content,
        )
    except Exception as exc:
        raise MemoryToolError(
            MemoryErrorCode.INVALID_ARGUMENT,
            "长期记忆参数无效",
            cause=exc,
        ) from exc

    now = datetime.now(timezone.utc)
    effective_memory_id = validated_args.memory_id or _new_memory_id()
    try:
        record = repository.upsert_memory(
            memory_id=effective_memory_id,
            project_id=project_id,
            content=validated_args.content,
            source_run_id=source_run_id,
            now=now,
            create=validated_args.memory_id is None,
        )
    except MemoryToolError:
        raise
    except ValueError as exc:
        raise MemoryToolError(
            MemoryErrorCode.INVALID_ARGUMENT,
            str(exc),
            cause=exc,
        ) from exc
    except Exception as exc:
        raise MemoryToolError(
            MemoryErrorCode.STORAGE_ERROR,
            "保存长期记忆失败",
            cause=exc,
        ) from exc
    return RememberOutput(
        memory_id=record.memory_id,
        content=record.content,
    )


def _new_memory_id() -> str:
    from uuid import uuid4

    return str(uuid4())


def _search_text(run: Run) -> str:
    return f"{run.prompt}\n{run.result or ''}"


def _to_result(
    run: Run,
    repository: MemoryRepository,
    *,
    include_process: bool,
) -> MemoryRunResult:
    process = None
    if include_process:
        try:
            #从 agent_run_message 解码 JSON 后返回 RunMessage 列表，无消息返回 []。
            messages = repository.list_messages(run.run_id)[:_MAX_PROCESS_MESSAGES]
        except Exception as exc:
            raise MemoryToolError(
                MemoryErrorCode.STORAGE_ERROR,
                "读取历史运行过程失败",
                cause=exc,
            ) from exc
        process = [
            MemoryProcessMessage(
                sequence=message.sequence,
                message_type=message.message_type,
                content=_display_process_content(message.message_type, message.content),
                created_at=message.created_at,
            )
            for message in messages
        ]
    return MemoryRunResult(
        run_id=run.run_id,
        created_at=run.created_at,
        status=run.status.value,
        prompt=_bounded_text(run.prompt),
        result=_bounded_text(run.result) if run.result is not None else None,
        process=process,
    )


def _display_process_content(message_type: str, content: Any) -> dict[str, Any] | str | None:
    """只暴露可回溯内容；reasoning 不返回 provider_item/encrypted_content。"""
    if message_type == "reasoning":
        if isinstance(content, dict):
            return {
                "display_text": _bounded_text(content.get("display_text")),
                "display_type": content.get("display_type", "reasoning_text"),
            }
        return {"display_text": _bounded_text(content), "display_type": "reasoning_text"}
    return _bounded_json(content)


def _bounded_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return text[:_MAX_CONTENT_CHARS]


def _bounded_json(value: Any) -> dict[str, Any] | str | None:
    if value is None or isinstance(value, (str, dict)):
        if isinstance(value, str):
            return _bounded_text(value)
        if isinstance(value, dict):
            encoded = json.dumps(value, ensure_ascii=False)
            if len(encoded) <= _MAX_CONTENT_CHARS:
                return value
            return {"truncated": True, "content": encoded[:_MAX_CONTENT_CHARS]}
        return value
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    return encoded[:_MAX_CONTENT_CHARS]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
