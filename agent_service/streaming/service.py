"""单 Python 进程内的 SSE 通道；不执行 Agent，不存每个文字片段。

RunService 发布状态，Runtime 通过 on_text(message_id, delta) 发布可见文字。
重连先取当前内容副本，再接收新事件；不使用 Last-Event-ID 回放历史。
所有发布/订阅登记都在应用事件循环调用，方法内部不 await，因此捕获副本与
登记队列之间不会插入一次发布。工具工作线程不能直接调用这些方法。
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from time import monotonic
from typing import Any, AsyncIterator

from ..runs.models import Run, RunStatus
from .exception import EventLimitError
from .models import VisibleRun


TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
PUBLIC_FAILURE = "任务执行失败，请通过运行 ID 查看服务端诊断"


@dataclass(eq=False)
class EventSubscription:
    """一个页面的一份队列；关闭它不取消任务，多个页面不会抢同一份消息。"""

    owner: "RunEvents"
    run_id: str
    first: dict[str, Any]
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    closed: bool = False

    def close(self) -> None:
        """幂等释放订阅名额，并唤醒仍在等待的读者。"""
        if self.closed:
            return
        self.closed = True
        self.owner.unsubscribe(self)
        # 丢弃的是已关闭页面的队列，不是运行的当前内容；重连能重新获取全文。
        while not self.queue.empty():
            self.queue.get_nowait()
        self.queue.put_nowait(None)

    async def frames(self) -> AsyncIterator[str]:
        """先发副本，再等新事件；心跳不访问数据库，finally 只清理订阅。"""
        started = monotonic()
        try:
            yield self.owner.encode(self.first)
            if self.first["event"] == "stream.error" or self.first["data"].get("status") in TERMINAL_STATUSES:
                return
            while not self.closed:
                remaining = self.owner.connection_seconds - (monotonic() - started)
                if remaining <= 0:
                    return  # 有界连接时长，到期由调用方重连并重新鉴权。
                try:
                    event = await asyncio.wait_for(
                        self.queue.get(), timeout=min(self.owner.heartbeat_seconds, remaining)
                    )
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if event is None:
                    return
                yield self.owner.encode(event)
                if event["event"] in {"run.completed", "run.failed", "run.cancelled", "stream.error"}:
                    return
        finally:
            self.close()


class RunEvents:
    """有界的当前运行内容和广播器，属于一个 RunService/应用实例。

    第一阶段只实现开始、文字增量、结束事件。工具/OSS 事件后续再接；快照中
    active_tool/files/warnings 先保留空值，避免未来改前端基础响应形状。
    默认上限是保护值，不是已经通过 50 人压测的容量承诺。
    工具提示阶段已接入开始/结束事件和 active_tool；files/warnings 仍保持原空值。
    """

    def __init__(
        self, *, max_runs: int = 128, max_subscribers: int = 128,
        per_run_subscribers: int = 2, queue_size: int = 64,
        max_text_bytes: int = 256_000, max_messages: int = 128,
        max_frame_bytes: int = 1_048_576, retention_seconds: float = 300,
        heartbeat_seconds: float = 15, connection_seconds: float = 1800,
    ) -> None:
        limits = (max_runs, max_subscribers, per_run_subscribers, queue_size,
                  max_text_bytes, max_messages, max_frame_bytes, retention_seconds,
                  heartbeat_seconds, connection_seconds)
        if any(value <= 0 for value in limits):
            raise ValueError("SSE 资源上限和时间必须大于零")
        self.max_runs = max_runs
        self.max_subscribers = max_subscribers
        self.per_run_subscribers = per_run_subscribers
        self.queue_size = queue_size
        self.max_text_bytes = max_text_bytes
        self.max_messages = max_messages
        self.max_frame_bytes = max_frame_bytes
        self.retention_seconds = retention_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.connection_seconds = connection_seconds
        self._runs: dict[str, VisibleRun] = {}
        self._subscribers: set[EventSubscription] = set()

    def register(self, run_id: str) -> None:
        """在任务落库前预留运行内容空间，满时拒绝，不创建无界等待记录。"""
        if run_id in self._runs:
            return
        now = monotonic()
        for key, visible in list(self._runs.items()):
            if visible.finished_at is not None and now - visible.finished_at >= self.retention_seconds:
                del self._runs[key]
        if len(self._runs) >= self.max_runs:
            # 终态数据可从数据库恢复；只淘汰最早终态，不淘汰活动运行。
            completed = [(value.finished_at, key) for key, value in self._runs.items()
                         if value.finished_at is not None]
            if not completed:
                raise EventLimitError("CAPACITY_EXCEEDED", "当前运行容量已满")
            del self._runs[min(completed)[1]]
        self._runs[run_id] = VisibleRun(status=RunStatus.CREATED)

    def discard(self, run_id: str) -> None:
        """仅用于创建任务落库失败时撤销预留，不删除数据库数据。"""
        self._runs.pop(run_id, None)

    def started(self, run_id: str) -> None:
        """状态保存成功后发布运行开始；不重复启动 Agent。"""
        visible = self._runs[run_id]
        if visible.status != RunStatus.CREATED:
            return
        visible.status = RunStatus.RUNNING
        self._publish(run_id, "run.started", {"status": RunStatus.RUNNING})

    def text(self, run_id: str, message_id: str, delta: str) -> None:
        """追加同一助手消息的增量；不写数据库，不接受任意事件名或原始模型对象。"""
        visible = self._runs[run_id]
        if visible.status != RunStatus.RUNNING:
            return
        if not isinstance(message_id, str) or not message_id or len(message_id) > 128:
            raise ValueError("可见消息 ID 必须是 1~128 字符")
        if not isinstance(delta, str):
            raise TypeError("可见文字必须是字符串")
        if not delta:
            return
        size = len(delta.encode("utf-8"))
        if visible.text_bytes + size > self.max_text_bytes or (
            message_id not in visible.messages and len(visible.messages) >= self.max_messages
        ):
            raise EventLimitError("OUTPUT_LIMIT_EXCEEDED", "运行可见文字超过上限")
        # 先检查单帧再更新当前内容，失败时不会留下“内容已变但事件未发”的半次更新。
        self.encode(self._event(run_id, "assistant.delta", visible.sequence + 1,
                                {"message_id": message_id, "delta": delta}))
        visible.messages[message_id] = visible.messages.get(message_id, "") + delta
        visible.text_bytes += size
        self._publish(run_id, "assistant.delta", {"message_id": message_id, "delta": delta})

    def finished(self, run: Run) -> None:
        """只在数据库终态保存成功后调用；原始异常不进入实时输出。"""
        visible = self._runs.get(run.run_id)
        if visible is None or visible.status in TERMINAL_STATUSES:
            return
        name = {RunStatus.COMPLETED: "run.completed", RunStatus.FAILED: "run.failed",
                RunStatus.CANCELLED: "run.cancelled"}[run.status]
        fields = {"status": run.status,
                  "result": run.result if run.status == RunStatus.COMPLETED else None,
                  "error": PUBLIC_FAILURE if run.status == RunStatus.FAILED else None}
        self.encode(self._event(run.run_id, name, visible.sequence + 1, fields))
        visible.status = run.status
        visible.active_tool = None
        visible.result = run.result if run.status == RunStatus.COMPLETED else None
        visible.error = PUBLIC_FAILURE if run.status == RunStatus.FAILED else None
        visible.finished_at = monotonic()
        self._publish(run.run_id, name, fields)

    def storage_failed(self, run_id: str) -> None:
        """收尾写库失败只报告通道错误，不能假装任务已可靠完成。"""
        if run_id in self._runs:
            fields = {
                "code": "PERSISTENCE_FAILED", "message": "任务状态保存失败，请检查服务端日志",
                "retryable": False,
            }
            self._runs[run_id].stream_error = fields
            self._publish(run_id, "stream.error", fields)

    def subscribe(self, run: Run) -> EventSubscription:
        """不 await 地捕获副本并登记独立队列；不会漏掉副本之后的增量。"""
        if len(self._subscribers) >= self.max_subscribers or sum(
            sub.run_id == run.run_id for sub in self._subscribers
        ) >= self.per_run_subscribers:
            raise EventLimitError("SUBSCRIPTION_LIMIT", "实时订阅连接数已达上限")
        visible = self._runs.get(run.run_id)
        if visible is not None and visible.stream_error is not None:
            first = self._event(run.run_id, "stream.error", visible.sequence, visible.stream_error)
        elif visible is None and run.status not in TERMINAL_STATUSES:
            first = self._event(run.run_id, "stream.error", 0, {
                "code": "STREAM_STATE_LOST", "message": "运行期实时内容不可恢复，请查询任务状态",
                "retryable": False,
            })
        else:
            # 内存过期/服务重启后，仅恢复已落库的最终结果；不谎称能恢复未保存片段。
            visible = visible or VisibleRun(
                status=run.status, result=run.result if run.status == RunStatus.COMPLETED else None,
                error=PUBLIC_FAILURE if run.status == RunStatus.FAILED else None,
            )
            first = self._event(run.run_id, "run.snapshot", visible.sequence, {
                "status": visible.status,
                "messages": [{"message_id": key, "text": value} for key, value in visible.messages.items()],
                "active_tool": dict(visible.active_tool) if visible.active_tool else None,
                "files": [], "warnings": [],
                "result": visible.result, "error": visible.error,
            })
        self.encode(first)  # 超大响应在 HTTP 握手前拒绝，不留下订阅名额。
        sub = EventSubscription(self, run.run_id, first, asyncio.Queue(maxsize=self.queue_size))
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, subscription: EventSubscription) -> None:
        """释放一个页面的连接名额，不碰任务状态和执行协程。"""
        self._subscribers.discard(subscription)

    def tool_started(self, run_id: str, call_id: str, tool_name: str) -> None:
        """工具实际执行前通知名称；只留当前工具，重连不再显示空白等待。"""
        visible = self._runs[run_id]
        if visible.status != RunStatus.RUNNING:
            return
        self._check_tool_identity(call_id, tool_name)
        if visible.active_tool is not None:
            raise ValueError("上一个工具尚未结束，不能覆盖当前工具提示")
        fields = {"call_id": call_id, "tool_name": tool_name}
        self.encode(self._event(run_id, "tool.started", visible.sequence + 1, fields))
        visible.active_tool = fields
        self._publish(run_id, "tool.started", fields)

    def tool_finished(
        self, run_id: str, call_id: str, tool_name: str,
        success: bool, error_code: str | None = None,
    ) -> None:
        """工具返回后通知结果；工具失败不改变整项任务的RUNNING状态。"""
        visible = self._runs[run_id]
        if visible.status != RunStatus.RUNNING:
            return
        self._check_tool_identity(call_id, tool_name)
        if visible.active_tool != {"call_id": call_id, "tool_name": tool_name}:
            raise ValueError("工具结束提示与当前执行工具不一致")
        # 错误码仅接受有界机器标识，避免把异常原文/路径误当成错误码发送。
        safe_code = error_code if isinstance(error_code, str) and re.fullmatch(
            r"[A-Z][A-Z0-9_]{0,63}", error_code
        ) else "TOOL_ERROR"
        fields = {"call_id": call_id, "tool_name": tool_name, "success": success,
                  "error_code": None if success else safe_code,
                  "error": None if success else "工具执行失败"}
        self.encode(self._event(run_id, "tool.finished", visible.sequence + 1, fields))
        visible.active_tool = None
        self._publish(run_id, "tool.finished", fields)

    @staticmethod
    def _check_tool_identity(call_id: str, tool_name: str) -> None:
        """限制提示字段的长度和格式，不接受原始工具参数或任意内容。"""
        if not isinstance(call_id, str) or not re.fullmatch(r"[A-Za-z0-9_:.\-]{1,256}", call_id):
            raise ValueError("工具提示调用编号不合法")
        if not isinstance(tool_name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", tool_name):
            raise ValueError("工具提示名称不合法")

    def close(self) -> None:
        """应用关闭时释放全部订阅和内容；不在这里取消 Agent。"""
        for subscription in tuple(self._subscribers):
            subscription.close()
        self._runs.clear()

    def encode(self, event: dict[str, Any]) -> str:
        """只编码受控事件名和单行 JSON，正文换行不会注入额外 SSE 帧。"""
        frame = (f"event: {event['event']}\nid: {event['data']['sequence']}\n"
                 f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n")
        if len(frame.encode("utf-8")) > self.max_frame_bytes:
            raise EventLimitError("FRAME_LIMIT_EXCEEDED", "实时事件大小超过上限")
        return frame

    def _event(self, run_id: str, name: str, sequence: int, fields: dict) -> dict:
        """组装内部统一信封；Java 后续只补 task_id/conversation_id，不重编号。"""
        return {"event": name, "data": {"run_id": run_id, "sequence": sequence,
                "created_at": datetime.now(timezone.utc).isoformat(), **fields}}

    def _publish(self, run_id: str, name: str, fields: dict) -> None:
        """更新序号并广播；慢页面队列满就关闭，不反压 Agent 或其他页面。"""
        visible = self._runs[run_id]
        event = self._event(run_id, name, visible.sequence + 1, fields)
        self.encode(event)
        visible.sequence += 1
        for subscription in tuple(self._subscribers):
            if subscription.run_id == run_id:
                try:
                    subscription.queue.put_nowait(event)
                except asyncio.QueueFull:
                    subscription.close()
