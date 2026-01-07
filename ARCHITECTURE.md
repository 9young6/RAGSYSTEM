# 架构与代码导览（RAG System）

本文档面向“二次开发/内网定制”场景，重点回答：
- 代码整体分层与目录结构是什么？
- 文档上传→转换→chunk→审核→入库→检索的链路分别在哪些文件里？
- 想改“文档审查（审核）”规则/页面/接口，应该改哪里？

> 运行与部署细节请配合阅读：`PROJECT_RUNBOOK.md`、`OFFLINE_DEPLOYMENT.md`。

---

## 1. 系统组件概览

**核心服务（docker compose）**
- `frontend`：静态前端（Nginx），提供 Web UI。
- `backend`：FastAPI（REST API），承载业务逻辑与鉴权。
- `celery_worker`：Celery 异步任务（PDF 转 Markdown、OCR 等）。
- `postgres`：元数据与可编辑内容（Document / Chunk / 审核记录 / 用户配置）。
- `milvus + etcd`：向量检索（只存向量与定位信息，不存正文）。
- `minio`：对象存储（原始文件、Markdown）。
- `redis`：Celery broker + 缓存。

**外部/可选推理后端（不一定在 compose 里）**
- `Ollama`：LLM + Embedding（本项目默认推荐：LLM `qwen2.5:32b`，Embedding `bge-large:latest`）。
- `Xinference`：OpenAI-compatible LLM（可选）+ Rerank（推荐：`bge-reranker-large`）。
- `vLLM`：OpenAI-compatible LLM（可选，适合内网统一 vLLM 环境）。

---

## 2. 目录结构与职责

**后端：`backend/`**
- `backend/main.py`：FastAPI 入口；启动时初始化 DB/Milvus/MinIO/管理员账号。
- `backend/app/config.py`：配置（从 `.env` 读取，Pydantic Settings）。
- `backend/app/api/`：API 路由层（权限/参数校验/返回结构）。
  - `documents.py`：上传/Markdown/Chunks/删除/列表。
  - `review.py`：管理员审核（pending/approve/reject）。
  - `query.py`：检索问答（用户查询/管理员跨库查询）。
  - `settings.py`：用户默认查询设置（provider/model/top_k/rerank 等）。
  - `admin.py`：用户清单、批量 reindex（运维）。
  - `diagnostics.py`：推理后端连通性测试（Ollama/vLLM/Xinference/rerank）。
- `backend/app/services/`：业务服务层（可被 API/任务复用）。
  - `rag_service.py`：索引与查询（Milvus 检索 + 可选 rerank + LLM 生成）。
  - `embedding_service.py`：embedding 生成（Ollama / sentence-transformers / hash）。
  - `llm_service.py`：LLM 生成（Ollama / OpenAI-compatible）。
  - `rerank_service.py`：rerank（Xinference /v1/rerank）。
  - `milvus_service.py`：Milvus collection/partition/CRUD。
  - `minio_service.py`：MinIO 上传/下载/路径约定（`user_{id}/...`）。
  - `chunk_service.py`：文本切分与 chunk 重建（落库 Postgres）。
- `backend/app/models/`：ORM 模型（核心：Document/DocumentChunk/ReviewAction/User/UserSettings）。
- `backend/tasks/`：Celery 入口与任务实现。
  - `celery_app.py`：Celery app 配置。
  - `mineru_tasks.py`：PDF→Markdown（MinerU/magic-pdf -> fallback -> OCR）+ 生成 chunks。

**前端：`frontend/`**
- `frontend/login.html`：登录/注册页。
- `frontend/app.html`：主界面（文档、上传、查询、审核、设置）。
- `frontend/js/api.js`：统一 API 客户端（携带 token、封装端点）。
- `frontend/js/documents.js`：文档列表 + chunk 管理（编辑/勾选 included/重建向量/删除）。
- `frontend/js/upload.js`：上传、预览、Markdown 下载/上传、确认提交。
- `frontend/js/review.js`：管理员审核页（待审核列表、通过/拒绝）。
- `frontend/js/query.js`：RAG 查询页（sources 展示、可选 rerank）。
- `frontend/js/settings.js`：推理后端与默认模型设置展示 + 连通性测试。

---

## 3. 关键数据模型（Postgres）

**`Document`（`backend/app/models/document.py`）**
- `status`：业务流程状态（uploaded/confirmed/rejected/approved/indexed）。
- `markdown_status`：转换状态（processing/markdown_ready/failed）。
- `owner_id`：多租户隔离关键字段（文档归属）。
- `minio_object`：原始文件对象路径。
- `markdown_path`：Markdown 对象路径（`user_{owner_id}/markdown/{document_id}.md`）。
- `reject_reason`：拒绝原因（用户可见，用于重新提交）。

**`DocumentChunk`（`backend/app/models/document_chunk.py`）**
- `document_id + chunk_index`：逻辑定位一个 chunk。
- `content`：chunk 文本（可编辑）。
- `included`：是否参与最终入库（写入 Milvus）。

**`ReviewAction`（`backend/app/models/review_action.py`）**
- 审核动作审计（approve/reject + reason + 时间 + reviewer）。

---

## 4. 文档生命周期（状态机）

**上传→转换（Markdown）**
1) 用户上传：`POST /api/v1/documents/upload`
   - 创建 `Document(status=uploaded, markdown_status=processing)`
   - 原始文件写入 MinIO
   - PDF：触发 Celery `convert_to_markdown(document_id)`
   - 非 PDF：同步生成 Markdown + chunks
2) 转换完成：`Document.markdown_status=markdown_ready` 且写入 `markdown_path`

**确认提交→审核→入库**
3) 用户确认提交：`POST /api/v1/documents/confirm/{id}`
   - 仅允许 `markdown_ready` 后提交，避免“待转换”进入审核
4) 管理员审核：
   - 待审核列表：`GET /api/v1/review/pending`
   - 通过：`POST /api/v1/review/approve/{id}` → 触发 `RAGService.index_document()` 写入 Milvus
   - 拒绝：`POST /api/v1/review/reject/{id}` → 写入 `reject_reason`
5) 入库完成：`Document.status=indexed`

> 重新提交：`rejected` 状态的文档，用户可修订 Markdown/Chunks 后再次 `confirm`。

---

## 5. “文档审查（审核）”要改哪里？

下面是内网最常见的改动点，按“改规则/改接口/改页面”分类给出入口。

### 5.1 改审核队列规则（哪些文档进入待审核）
- 后端：`backend/app/api/review.py`
  - `get_pending_reviews()`：默认只取 `status=confirmed && markdown_status=markdown_ready`
  - 你可以按需加入：按 owner 白名单、按文件类型、按大小、按风险等级等

### 5.2 改“确认提交”规则（用户什么时候能提交给管理员）
- 后端：`backend/app/api/documents.py`
  - `confirm_document()`：默认要求 `markdown_status=markdown_ready`
  - 你可以扩展：强制用户上传手工修订的 Markdown、强制至少编辑过 N 个 chunk 等

### 5.3 改“通过/拒绝”后的行为（是否自动索引、是否接外部审批）
- 后端：`backend/app/api/review.py`
  - `approve_document()`：默认立即 `RAGService.index_document()` 写入 Milvus
  - `reject_document()`：默认只写状态与原因
- 审计：`backend/app/models/review_action.py`
  - 如需更多动作类型：扩展 `action` 枚举/约定，并同步前端交互

### 5.4 改“chunk 审核/勾选 included/编辑后的入库规则”
- chunk 重建/切分：`backend/app/services/chunk_service.py`、`backend/app/services/text_splitter.py`
- 入库使用 included：`backend/app/services/rag_service.py#index_document`
- 前端 chunk 管理：`frontend/js/documents.js`

---

## 6. 推理后端配置与可测试性

**配置来源**
- 服务端统一从 `.env` 读取（`backend/app/config.py`）
- 前端“设置”页通过 API 展示默认值：`GET /api/v1/settings/me`

**连通性测试（推荐上线前必跑）**
- Ollama：`POST /api/v1/diagnostics/ollama`
- 任意 provider（ollama/vllm/xinference）：`POST /api/v1/diagnostics/inference`
- Rerank（xinference）：`POST /api/v1/diagnostics/rerank`

---

## 7. 调试建议（内网/镜像环境）

**后端/任务日志**
- `docker compose logs --tail 200 backend`
- `docker compose logs --tail 200 celery_worker`

**常见排障入口**
- MinIO：`docker compose logs --tail 200 minio`
- Milvus：`docker compose logs --tail 200 milvus`
- 健康检查：`GET /api/v1/health`
- 向量丢失重建：`POST /api/v1/admin/reindex`

