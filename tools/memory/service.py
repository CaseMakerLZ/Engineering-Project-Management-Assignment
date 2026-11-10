"""search_memory 的历史回溯与结果裁剪，以及 remember 的项目长期记忆写入。"""

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from agent.exception import public_failure_message
from agent_service.runs.models import Run, RunStatus, RunMessage
from agent.message import MessageType
from llm.mapper import reasoning_display_content
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
    run_id: str | None = None,
    match_text: str | None = None,
    fuzzy_match: bool = False,
    time_range: dict[str, Any] | None = None,
    limit: int = 5,
    include_process: bool = False,
    process_offset: int = 0,
    process_sequence: int | None = None,
    content_offset: int = 0,
    repository: MemoryRepository,
    project_id: str,
    conversation_id: str | None,
    before_created_at: datetime,
    current_state=None,
    current_run_id: str | None = None,
    current_prompt: str | None = None,
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
        run_id=run_id,
        match_text=match_text,
        fuzzy_match=fuzzy_match,
        time_range=time_range or {},
        limit=limit,
        include_process=include_process,
        process_offset=process_offset,
        process_sequence=process_sequence,
        content_offset=content_offset,
    )
    match_text = validated_args.match_text
    fuzzy_match = validated_args.fuzzy_match
    limit = validated_args.limit
    include_process = validated_args.include_process
    run_id = validated_args.run_id
    process_offset = validated_args.process_offset
    process_sequence = validated_args.process_sequence
    content_offset = validated_args.content_offset
    parsed_range = validated_args.time_range
    before = _as_utc(before_created_at)
    # 只能显式读取服务端绑定的当前运行；不把它混入默认历史查询。
    # state.history从未压缩，故本轮尚未落库的过程也能找回。
    if run_id is not None and run_id == current_run_id and current_state is not None:
        messages = None
        if include_process:
            messages = []
            for index, message in enumerate(list(current_state.history[current_state.initial_history_length:]), 1):
                content = message.content
                if message.type == MessageType.REASONING:
                    text, display_type = reasoning_display_content(content)
                    content = {"display_text": text, "display_type": display_type}
                messages.append(RunMessage(sequence=index, message_type=message.type.value,
                                           content=content, created_at=before))
        current = Run(run_id=run_id, project_id=project_id, conversation_id=conversation_id,
                      prompt=current_prompt or "", status=RunStatus.RUNNING, result=None,
                      error=None, created_at=before)
        result = _to_result(current, repository, include_process=include_process,
                            process_offset=process_offset, process_messages=messages,
                            process_sequence=process_sequence, content_offset=content_offset)
        return SearchMemoryOutput(results=[result], returned_count=1, has_more=False, truncated=False)
    end = _as_utc(parsed_range.end) if parsed_range.end is not None else before
    end = min(end, before)
    if parsed_range.start is not None:
        start = _as_utc(parsed_range.start)
    elif run_id is not None:
        # MySQL DATETIME 的下限是1000年；精确回溯不受默认最近一周限制。
        start = datetime(1000, 1, 1, tzinfo=timezone.utc)
    else:
        start = end - timedelta(days=7)
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
            run_id=run_id,
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
        _to_result(run, repository, include_process=include_process, process_offset=process_offset,
                   process_sequence=process_sequence, content_offset=content_offset)
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
    process_offset: int,
    process_messages: list[RunMessage] | None = None,
    process_sequence: int | None = None,
    content_offset: int = 0,
) -> MemoryRunResult:
    process = None
    process_total = None
    process_next_offset = None
    if include_process:
        try:
            #从 agent_run_message 解码 JSON 后返回 RunMessage 列表，无消息返回 []。
            messages = (process_messages if process_messages is not None
                        else repository.list_messages(run.run_id))
        except Exception as exc:
            raise MemoryToolError(
                MemoryErrorCode.STORAGE_ERROR,
                "读取历史运行过程失败",
                cause=exc,
            ) from exc
        # 默认看最后做过什么；往前翻页时仍保持每一段内部从旧到新的顺序。
        process_total = len(messages)
        end = max(0, process_total - process_offset)
        start = max(0, end - _MAX_PROCESS_MESSAGES)
        if start > 0:
            process_next_offset = process_offset + (end - start)
        selected = messages[start:end] if process_sequence is None else [
            message for message in messages if message.sequence == process_sequence]
        if process_sequence is not None:
            process_next_offset = None
        process = []
        for message in selected:
            # reasoning只展示服务商明确给出的可读内容，不分页暴露原始加密项。
            raw = message.content
            if message.message_type == "reasoning":
                raw = ({"display_text": raw.get("display_text"),
                        "display_type": raw.get("display_type", "reasoning_text")}
                       if isinstance(raw, dict) else {"display_text": raw})
            # 工具结果按output正文翻页，偏移与工作上下文的预览字符位置一致。
            if message.message_type == "tool_result" and isinstance(raw, dict) and isinstance(raw.get("output"), str):
                raw = raw["output"]
            text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False, default=str)
            next_offset = content_offset + _MAX_CONTENT_CHARS if len(text) > content_offset + _MAX_CONTENT_CHARS else None
            content = (text[content_offset:content_offset + _MAX_CONTENT_CHARS] if process_sequence is not None or len(text) > _MAX_CONTENT_CHARS
                       else _display_process_content(message.message_type, message.content))
            process.append(MemoryProcessMessage(
                sequence=message.sequence,
                message_type=message.message_type,
                content=content,
                created_at=message.created_at,
                content_total_chars=len(text),
                content_next_offset=next_offset,
            ))
    return MemoryRunResult(
        run_id=run.run_id,
        created_at=run.created_at,
        status=run.status.value,
        prompt=_bounded_text(run.prompt),
        result=_bounded_text(run.result) if run.result is not None else None,
        error=public_failure_message(run.error) if run.status == RunStatus.FAILED else None,
        process=process,
        process_total=process_total,
        process_next_offset=process_next_offset,
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
