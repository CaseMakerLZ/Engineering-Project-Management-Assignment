# Java Spring Boot 调用契约

服务默认地址：`http://127.0.0.1:8000`

接口前缀：`/api/internal`

## 健康检查

```http
GET /api/internal/health
```

响应 `200`：

```json
{"status": "ok", "service": "python-agent-service"}
```

## 创建 Agent 任务

```http
POST /api/internal/runs
Content-Type: application/json
X-Service-Token: <optional-token>
```

请求体：

```json
{
  "project_id": "project-001",
  "prompt": "分析当前项目的代码结构"
}
```

响应 `202`：

```json
{
  "run_id": "uuid",
  "status": "CREATED"
}
```

Java 应保存 `run_id`，随后轮询状态。

## 查询任务

```http
GET /api/internal/runs/{run_id}
```

响应 `200`：

```json
{
  "run_id": "uuid",
  "project_id": "project-001",
  "prompt": "分析当前项目的代码结构",
  "status": "RUNNING",
  "result": null,
  "error": null,
  "created_at": "2026-09-22T12:00:00Z",
  "started_at": "2026-09-22T12:00:01Z",
  "finished_at": null
}
```

状态枚举：`CREATED`、`RUNNING`、`COMPLETED`、`FAILED`、`CANCELLED`。

## 查询消息

```http
GET /api/internal/runs/{run_id}/messages
```

响应包含按 `sequence` 排序的 Agent 消息。Java 不需要理解 OpenAI SDK 类型，只处理 `message_type` 和 JSON `content`。

## 取消任务

```http
POST /api/internal/runs/{run_id}/cancel
```

取消只对未完成任务生效。当前版本的取消是状态层面的最小实现；正在执行的外部 LLM 请求不会被强制中断。

## 错误

资源不存在返回 `404`。启用 `AGENT_SERVICE_INTERNAL_TOKEN` 后，缺少或错误的 `X-Service-Token` 返回 `401`。
