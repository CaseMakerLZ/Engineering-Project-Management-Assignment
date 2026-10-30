# AgentDesk Frontend

React 19 + TypeScript + Vite 前端。浏览器只访问 Java 后端 `/api/**`，不连接
Python、数据库、Redis 或 OSS，也不读取内部服务令牌。

## 本周前端能力

- 使用带 Bearer 的 `fetch` 持续读取任务 SSE，不把令牌放入 URL，也不读取整段
  `response.text()`。
- SSE 解析兼容中文/JSON 跨网络块、一块多帧、CRLF、多行 `data`、heartbeat 和未完成帧大小上限。
- `run.snapshot` 替换当前显示，增量文字按 `message_id` 追加，重复序号忽略，
  `stream.error` 优先处理。
- 任务 `RUNNING` 时显示过程和工具状态；工具失败只标记该调用，不把任务改成失败。
- 终态展示最终答案并关闭连接；断线约 1/2/4 秒最多重连三次，随后只做一次普通任务查询，
  保留手动重连入口，不恢复定时轮询。
- 云端项目提供右侧只读文件树、UTF-8 文本预览、单文件下载和项目 ZIP 下载；窄屏改为抽屉。
- 文件读取具备目录/正文缓存、在途请求合并、过期响应隔离、10 MiB/20 文件 LRU 限制；
  任务任一终态后清空缓存并刷新当前可见目录与已打开文件。
- Markdown 只拦截同源且严格匹配 `/api/projects/{projectId}/files/download?path=...` 的链接，
  下载时使用 Bearer；普通外链保留原行为。
- 本地模式创建项目时通过 Java 返回的允许根逐层点选文件夹，支持空目录、手动加载更多和新建
  单层文件夹，最终只读回显 `absolute_path` 并自动填入原 `local_path`。cloud 页面不请求本机目录接口。
- 创建入口提供“新建空白项目”和“从本地文件夹创建”两种方式；本地文件夹方式会预填目录名称，
  但不会复制或上传现有文件。cloud 因缺少上传/导入接口会明确禁用本地导入方式。
- 保留登录、项目、对话、Markdown/GFM、KaTeX、代码块、响应式和错误处理。

## 启动

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

开发服务器默认是 `http://127.0.0.1:5173`，`/api` 代理到
`http://127.0.0.1:8080`。

```env
# 云端：启用登录、Bearer、项目文件面板。
VITE_APP_MODE=cloud
VITE_API_BASE_URL=

# 本地：不显示登录，创建项目时使用目录点选。
# VITE_APP_MODE=local
```

## 命令

```bash
npm run typecheck
npm run build

# 本地固定夹具测试（按项目规则 tests/ 不提交）
node --experimental-strip-types --test tests/frontend-core.test.mjs
```

测试使用 Node.js 内置测试运行器和 TypeScript type stripping，不增加测试框架依赖。
建议使用 Node.js 22 或项目依赖所要求的更新版本。测试文件按仓库规则保留在本地。

## 接口映射

| 场景 | 接口 |
| --- | --- |
| 登录 / 注册 / 当前用户 / 退出 | `/api/auth/*` |
| 项目列表 / 创建 / 详情 | `/api/projects`、`/api/projects/{projectId}` |
| 对话 | `/api/projects/{projectId}/conversations` |
| 提交任务 | `POST /api/conversations/{conversationId}/turns` |
| 任务补偿查询 | `GET /api/conversations/{conversationId}/turns/{taskId}` |
| 任务实时事件 | `GET /api/conversations/{conversationId}/turns/{taskId}/events` |
| 云端目录 | `GET /api/projects/{projectId}/files/tree` |
| 云端文本预览 | `GET /api/projects/{projectId}/files/content` |
| 单文件下载 | `GET /api/projects/{projectId}/files/download` |
| 项目 ZIP | `GET /api/projects/{projectId}/archive` |
| 本地目录浏览 / 创建 | `GET/POST /api/local/directories` |

SSE 需要 Java 返回 `Content-Type: text/event-stream`。云端文件响应需要允许前端读取
`Content-Disposition`。跨域部署时还需为以上接口和 `Authorization` 配置 CORS。

## 验证状态

- 本地核心测试：8 项通过，覆盖中文跨字节、多帧/CRLF/多行 data、快照替换、重复序号、工具失败、
  终态结果、空闲断线、安全下载链接和本地文件夹名校验。
- TypeScript 静态检查通过。
- 当前 Codex Windows 沙箱拒绝启动 TypeScript 7 与 Rolldown 的原生二进制，因此本次未能完成
  `vite build` 和浏览器截图；需在普通 Node.js 22 开发环境执行类型检查、上述测试命令和 `npm run build`。
- 真实 SSE、Java 文件接口和本机目录点选仍需由组长在前后端同一环境联调；仓库未加入假项目、
  假目录、假回答、令牌或真实配置。

## 主要目录

```text
src/
├─ api/
│  ├─ turnEvents.ts          # 带 Bearer 的 SSE 握手
│  ├─ files.ts               # 文件树、预览、Blob 下载
│  └─ localDirectories.ts    # 本地目录浏览与创建
├─ hooks/
│  ├─ useTurnStream.ts       # 单任务连接、归并、有限重连
│  └─ useProjectFiles.ts     # 文件缓存、去重、刷新与 LRU
├─ lib/
│  ├─ sseParser.ts           # 可独立测试的 SSE 帧解析
│  ├─ turnEventReducer.ts    # 纯事件状态归并
│  └─ protectedLinks.ts      # 严格本站下载链接识别
├─ components/
│  ├─ ProjectFilesPanel.tsx
│  └─ DirectoryPicker.tsx
└─ pages/ConversationPage.tsx
```
