# Python Agent Service

这是正式项目的 Python HTTP 服务边界，面向 Java Spring Boot 后端提供内部 API。它与 `examples/` 中的学习代码分离，也不改变现有 `agent/` 手写 Agent Core 的学习实现。

## 架构

```text
Java Spring Boot
        │ HTTP/JSON
        ▼
agent_service.api
        ▼
agent_service.service.RunService
        ├── MySQLRunRepository
        └── AgentRuntime
                ▼
          当前 agent/ 核心
```

`AgentRuntime` 是编排层适配点。以后迁移到 LangGraph，只需替换 runtime 实现，Java API 和任务持久化契约保持不变。

## API

所有接口前缀为 `/api/internal`：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/health` | 服务健康检查 |
| POST | `/runs` | 创建 Agent 运行，返回 `202` 和 `run_id` |
| GET | `/runs/{run_id}` | 查询任务状态与结果 |
| GET | `/runs/{run_id}/messages` | 查询 Agent 消息 |
| POST | `/runs/{run_id}/cancel` | 取消尚未完成的任务 |

创建任务请求：

```json
{"project_id": "project-001", "prompt": "分析当前项目"}
```

任务状态：

```text
CREATED → RUNNING → COMPLETED
                    └→ FAILED
                    └→ CANCELLED
```

## 运行

在 PyCharm 中将 `agent_service/run_server.py` 作为模块运行，或将项目根目录作为工作目录后运行该文件。服务默认监听 `127.0.0.1:8000`，文档位于 `/docs`。

环境变量：

- `AGENT_SERVICE_INTERNAL_TOKEN`：可选。设置后 Java 必须在 `X-Service-Token` 请求头中携带相同值

当前默认 runtime 会调用现有 LLM 配置。接口层测试可以注入 fake runtime 和内存 Repository，不需要真实 API Key 或 MySQL。

MySQL 配置环境变量：

- `AGENT_SERVICE_MYSQL_HOST`：默认 `127.0.0.1`
- `AGENT_SERVICE_MYSQL_PORT`：默认 `3306`
- `AGENT_SERVICE_MYSQL_USER`：默认 `root`
- `AGENT_SERVICE_MYSQL_PASSWORD`：默认 `123456`
- `AGENT_SERVICE_MYSQL_DATABASE`：默认 `agent_javabackend`

生产数据只使用 MySQL 的 `agent_run` 和 `agent_run_message` 两张表；测试通过内存 Repository 注入，不连接数据库。
