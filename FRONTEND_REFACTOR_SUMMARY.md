# 前端架构说明与定制指南

本文档面向“内网定制/二次开发”，说明当前前端的页面结构、模块划分、与后端接口的对应关系，以及最常见的改动点（尤其是文档审核相关）。

> 后端整体架构与文件入口请同时参考：`ARCHITECTURE.md`。

---

## 1. 页面与导航（app.html）

主界面：`frontend/app.html`，左侧导航包含：
- **我的知识库**：文档列表 + 删除 + Chunk 管理（编辑/勾选 included/重建向量）。
- **上传文件**：上传原始文件、查看预览、等待/重试 Markdown 转换、下载/上传 Markdown、确认提交审核。
- **知识库查询**：RAG 查询（Milvus 检索 + 可选 rerank + LLM 生成），展示 sources。
- **验收审查**：上传验收材料、生成审查报告（Markdown），支持管理员范围扩展。
- **文档审核（管理员）**：待审核列表、通过/拒绝（管理员可见）。
- **设置**：用户默认模型参数、后端推理配置展示、连通性测试（diagnostics）。

权限控制：
- 是否显示“文档审核”等管理员功能，由前端 `API.isAdmin()` 判断，并在 UI 上隐藏（同时后端也会做强制鉴权）。

---

## 2. JS 模块划分（frontend/js）

### 2.1 基础模块
- `config.js`：全局配置（API base、存储键等）。
- `utils.js`：通用工具（DOM、时间/大小格式化、状态徽章、消息提示等）。
- `api.js`：统一 API 客户端（token 注入、请求封装、端点分组）。
- `auth.js`：登录/注册页逻辑（`login.html` 使用）。
- `app.js`：主应用“路由/页面切换”、用户信息、退出登录、初始化各页面模块。

### 2.2 功能模块
- `documents.js`：文档列表 + 批量删除 + Chunk 管理弹窗（CRUD、included 勾选、reembed）。
- `upload.js`：上传与 Markdown 工作流（轮询 markdown_status、下载/上传、确认提交）。
- `review.js`：管理员审核（加载待审核列表、通过/拒绝）。
- `query.js`：RAG 查询（provider/model/top_k/temperature/rerank），结果与 sources 展示。
- `settings.js`：用户默认设置保存、服务端默认值展示、连通性测试按钮。
- `acceptance.js`：验收审查工作流（上传材料、转换 Markdown、生成报告、下载）。

---

## 3. 与后端 API 的对应关系

后端 API base：默认 `http://<host>:8001/api/v1`（详见 `PROJECT_RUNBOOK.md`）。

主要端点映射：
- 登录/注册：`/auth/login`、`/auth/register`
- 文档：`/documents/*`（上传、列表、删除、Markdown、Chunks）
- 审核：`/review/*`
- 查询：`/query`、`/query/admin`
- 设置：`/settings/me`
- 诊断：`/diagnostics/*`
- 运维：`/admin/users`、`/admin/reindex`

---

## 4. 重点：文档审核（Review）定制入口

### 4.1 前端改哪里
- 页面逻辑：`frontend/js/review.js`
  - `loadPendingReviews()`：拉取待审核列表
  - `approveDocument()` / `rejectDocument()`：触发审核动作
- API 封装：`frontend/js/api.js`（通常是 `API.review.*`）

常见定制示例：
- 审核列表增加字段（owner、chunk 数、风险评分等）：修改 `review.js` 的渲染 + 后端 `GET /review/pending` 返回结构。
- “通过”弹出二次确认/要求选择策略：修改 `review.js` 的交互，再调用同一个 approve 接口或新增后端接口。

### 4.2 后端对应改哪里
- 审核接口：`backend/app/api/review.py`
- 审核动作审计：`backend/app/models/review_action.py`
- 文档状态/字段：`backend/app/models/document.py`

---

## 5. Chunk 管理（Documents → Chunk Modal）

Chunk 管理弹窗在 `frontend/app.html` 中定义，逻辑在：
- `frontend/js/documents.js`：chunk 列表、编辑、included 勾选、删除、新增、重建向量
- 后端：`backend/app/api/documents.py`（`/documents/{id}/chunks*`）

约定：
- **Postgres 存 chunk 正文（可编辑）**；**Milvus 只存向量**。
- `included=false` 的 chunk 不会参与入库索引（`RAGService.index_document()` 只取 included=true）。
- 对“已入库（indexed）”文档修改 chunk 后，如果希望检索立即生效，需要重建向量（reembed 或管理员 reindex）。

---

## 6. 设置页与连通性测试

设置页的两个概念：
- **用户默认值**（可保存）：默认 provider/model/top_k/temperature/rerank（后端表：UserSettings）。
- **服务端默认配置**（只展示）：来自 `.env`，包括 Ollama/vLLM/Xinference base_url 与 embedding 配置。

连通性测试按钮对应后端：
- `POST /diagnostics/ollama`
- `POST /diagnostics/inference`
- `POST /diagnostics/rerank`

---

## 7. 前端调试建议（内网/镜像环境）

推荐调试方式：
- **开发态**：`docker compose up -d --build`（默认挂载 `frontend/` 到容器内，改代码刷新即可生效）
- **定位 API 问题**：浏览器 DevTools Network 看请求路径与返回值；后端看 `docker compose logs --tail 200 backend`

常见问题：
- “Failed to fetch”：通常是 API base 配错、后端未启动、或 CORS/网络不可达。
- 列表/下载失败：优先看后端日志（MinIO/Milvus/推理后端不可达时会有明确错误信息）。

