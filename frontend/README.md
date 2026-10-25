# AgentDesk Frontend

课程项目「AI-Agent Helper」的前端工作区。技术栈为 **React 19 + TypeScript + Vite**，只调用 Java 后端 `/api/**`，不直接访问 Python `/api/internal/**`。

## 我负责的前端任务

结合《本周任务完整版》和《接口文档》，前端需要完成以下内容：

1. 设计并实现简洁、完整的页面视觉与响应式布局。
2. 统一封装 API 请求：基础地址、JSON、Bearer token、`Result<T>`、HTTP 状态码和业务码。
3. 项目页：获取项目列表、创建项目、查看项目详情；没有项目时显示真实空状态。
4. 对话页：创建对话、对话列表、对话详情、历史任务列表。
5. 提交任务：调用 `POST /api/conversations/{id}/turns`，保存响应中的 `task_id`。
6. 轮询任务：处理 `CREATED / RUNNING / COMPLETED / FAILED / CANCELLED`，且必须有停止条件。
7. 错误处理：10001、10002、10003、10004、10005、30005、40001、40002、50000。
8. Markdown 渲染、GFM 表格、代码块以及 KaTeX 数学公式。
9. 本地模式不显示登录流程；云端模式提供注册、登录、退出登录和 token 自动携带。
10. 不在页面写死项目、对话、任务或 Agent 回答。

## 已完成的功能

- **认证**：云端登录、注册、当前用户恢复、退出登录；token 内存 + `localStorage` 持久化，并记录过期时间兜底。
- **全局鉴权拦截**：HTTP 401 或业务码 `10002` 自动清 token、提示并跳转登录页；登录失败 `20002` 不会被误判为会话失效。
- **项目**：项目列表、空状态、创建项目、项目详情、最近对话和项目概览。
- **对话**：对话列表、搜索、新建对话、历史记录、对话详情。
- **异步任务**：`202` 提交后在本地立即显示服务端 `task_id` 的等待卡；自动轮询并更新为执行中/完成/失败/取消。
- **轮询保护**：首次 1.5 秒、递增退避、最长 5 秒间隔；终态、组件卸载或最长 180 秒后停止；超时后由用户手动继续查询。
- **防重复提交**：存在未完成任务时禁用输入；后端返回 `30005` 时刷新当前对话，保留已有任务卡。
- **错误体验**：字段错误贴近输入区域；`40001/40002/50000` 提供重试；任务错误使用纯文本展示。
- **内容渲染**：Markdown、表格、任务列表、代码块、链接、行内/块级 KaTeX 公式；回答支持一键复制。
- **响应式**：桌面三栏工作台；中小屏项目/对话侧栏抽屉；390×844 已实测。
- **可访问性**：语义化按钮、表单标签、`aria-invalid`、对话框 `role`、焦点样式、`prefers-reduced-motion`。

## 目录结构

```text
frontend/
├─ src/
│  ├─ api/                 # 统一请求层与按领域拆分的接口函数
│  ├─ auth/                # 登录状态、路由守卫
│  ├─ components/          # 布局、对话框、消息卡、输入框、Toast 等
│  ├─ hooks/               # 任务轮询
│  ├─ lib/                 # token、错误映射、格式化和校验
│  ├─ pages/               # 登录、注册、项目、项目首页、对话、404
│  ├─ styles/              # 设计变量、基础样式、各页面样式和响应式
│  ├─ types/               # 接口数据的 TypeScript 类型
│  ├─ App.tsx
│  └─ main.tsx
├─ .env.example
├─ vite.config.ts
└─ README.md
```

## 启动方式

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

开发服务器默认监听 `http://127.0.0.1:5173`，Vite 会把 `/api` 代理到 Java 后端 `http://127.0.0.1:8080`。

### 本地模式

```env
VITE_APP_MODE=local
VITE_API_BASE_URL=
```

- 不出现登录/注册路由，直接进入工作区。
- 创建项目时表单会显示 **项目目录**，并提交 `local_path`，符合当前 Java 后端 local profile 的校验。
- 该字段必须填写 Java 后端所在机器上真实存在的目录。

### 云端模式

```env
VITE_APP_MODE=cloud
VITE_API_BASE_URL=
```

- 启用 `/login`、`/register`、`/auth/me`、`/auth/logout` 流程。
- 请求会自动附带 `Authorization: Bearer <token>`。
- Vite 环境变量在启动/构建时读取；切换模式后需要重启开发服务器。

### 生产构建

```bash
npm run typecheck
npm run build
```

`dist/` 可以部署到与 Java 后端相同的域名下；若前后端分属不同域名，需要：

1. 设置 `VITE_API_BASE_URL=https://your-java-backend`；
2. 在 Java 后端配置允许前端域名的 CORS。

## 接口映射

| 场景 | 接口 |
| --- | --- |
| 注册 | `POST /api/auth/register` |
| 登录 | `POST /api/auth/login` |
| 当前用户 | `GET /api/auth/me` |
| 退出 | `POST /api/auth/logout` |
| 项目列表 | `GET /api/projects` |
| 创建项目 | `POST /api/projects` |
| 项目详情 | `GET /api/projects/{projectId}` |
| 对话列表 | `GET /api/projects/{projectId}/conversations` |
| 创建对话 | `POST /api/projects/{projectId}/conversations` |
| 对话详情 | `GET /api/conversations/{conversationId}` |
| 历史任务 | `GET /api/conversations/{conversationId}/turns` |
| 提交任务 | `POST /api/conversations/{conversationId}/turns` |
| 查询任务 | `GET /api/conversations/{conversationId}/turns/{taskId}` |

所有接口都经过 `src/api/client.ts`。该层会同时检查：

- HTTP 状态是否为 2xx；
- `Result<T>` 的 `code` 是否为 `0`；
- 错误时抛出带有 `status / code / data` 的 `ApiError`；
- 无需每个页面重复处理 `10002`。

## 验收自查

- `npm run typecheck` 通过。
- `npm run build` 通过。
- 使用临时 mock API 实测：登录 → 项目 → 项目首页 → 对话 → 提交任务 → `RUNNING` → `COMPLETED`。
- Markdown 表格、代码块、行内公式和块级公式均正常渲染。
- 桌面 1440×960 与移动端 390×844 布局正常。
- 401 + `10002` 时 token 被清除并自动跳转 `/login`。
- 浏览器控制台无运行时错误。

## 联调提醒

前端按《接口文档》完成。以仓库当前 `master`（提交 `27c46b3`）为基线，联调前还需要后端补齐以下内容：

- `GET /api/projects` 项目列表接口目前尚未实现，`ProjectController` 只有创建和详情。
- `UserController` 的认证接口仍是不完整占位代码，需要成员三完成注册、登录、`me`、退出登录。
- 若前端与 Java 不同源部署，需要补充 CORS 配置；使用 Vite 代理或同源静态部署时不需要。

这些都位于后端职责范围，本前端目录没有写入任何假项目、假对话或假 Agent 回答。
