# 企业级多租户文档知识库 RAG 系统设计

本文档描述系统“为什么这么设计”和“设计边界是什么”。代码层入口与定制点请看：`ARCHITECTURE.md`。

---

## 1. 目标与非目标

### 1.1 目标
- **多租户隔离**：普通用户只能访问自己的知识库；管理员可跨库管理与检索。
- **可离线交付**：外网构建镜像 → 内网导入运行，不依赖内网拉取新镜像。
- **文档可审核**：用户上传 → 生成 Markdown/Chunks → 管理员审核 → 才允许入库检索。
- **可编辑入库内容**：入库前即可在 chunk 级别编辑/删除/新增，并决定哪些 chunks 参与入库（included）。
- **推理后端可替换**：支持 Ollama / Xinference / vLLM（OpenAI-compatible）等部署形态。

### 1.2 非目标（当前版本不覆盖）
- 不做复杂的工作流编排（多级审批、多人会签）——可在定制中扩展。
- 不做全文检索（BM25）与向量混检——当前以 Milvus 向量检索为主。
- 不做细粒度 ACL（到文档/字段级授权）——当前以租户级隔离 + 管理员跨库为主。

---

## 2. 组件与依赖

**服务（docker compose）**
- `backend`（FastAPI）：业务 API、鉴权、索引与检索编排
- `celery_worker`（Celery）：PDF 转换、OCR 等异步任务
- `postgres`：元数据（文档/审核/用户设置）与 chunk 正文（可编辑）
- `milvus + etcd`：向量检索（仅存向量与定位信息）
- `minio`：对象存储（原始文件与 Markdown）
- `redis`：Celery broker

**推理后端（可外置）**
- **Ollama**：LLM + embedding（默认推荐组合）
- **Xinference**：rerank（推荐）与可选 LLM（OpenAI-compatible）
- **vLLM**：可选 LLM（OpenAI-compatible）

---

## 3. 总体架构（逻辑视图）

```
          ┌──────────────┐
          │   Frontend   │  (静态页 + JS)
          └──────┬───────┘
                 │ HTTP/JSON
          ┌──────▼───────┐
          │   Backend    │  FastAPI
          │  (Auth/API)  │
          └──┬─────┬─────┘
             │     │
      文档/状态     │ RAG 查询/索引
             │     │
   ┌─────────▼─┐  ┌▼─────────┐
   │ Postgres   │  │  Milvus   │  (向量)
   │ (metadata  │  │ partition │
   │  + chunks) │  │ per user  │
   └─────────┬──┘  └────┬──────┘
             │          │
             │          │
   ┌─────────▼──┐       │
   │   MinIO     │       │
   │ raw + md    │       │
   └─────────┬───┘       │
             │           │
      ┌──────▼──────┐    │
      │ Celery Worker │   │
      │ (MinerU/OCR)  │   │
      └──────────────┘   │
                          │
      ┌───────────────────▼───────────────────┐
      │ Inference Providers (External/Optional)│
      │  Ollama / Xinference / vLLM            │
      └────────────────────────────────────────┘
```

---

## 4. 数据模型（概念）

### 4.1 Document（文档元数据 + 流程状态）
- `status`：业务流程状态（uploaded/confirmed/rejected/approved/indexed）
- `markdown_status`：转换状态（processing/markdown_ready/failed）
- `owner_id`：租户隔离关键字段
- `minio_object`：原始文件路径
- `markdown_path`：Markdown 路径
- `reject_reason`：拒绝原因（用户可见）

### 4.2 DocumentChunk（可编辑的入库单元）
- `content`：chunk 文本（可编辑）
- `included`：是否参与入库（写入 Milvus）
- `chunk_index`：文档内顺序索引

### 4.3 ReviewAction（审计）
- `approve/reject` 动作、reviewer、时间、reason（可扩展）

---

## 5. 文档摄取（Upload → Markdown → Chunks → Review → Index）

### 5.1 设计原则
- **先可读后入库**：先把文档转换成可读/可编辑的 Markdown + chunk，再进入审核/索引。
- **正文不进向量库**：Milvus 只存向量与定位；正文以 Postgres chunk 为准（可编辑、可审计）。
- **失败可解释**：转换失败应有 `markdown_error`；前端可提示并允许重试/替换 Markdown。

### 5.2 处理链路（简化时序）
1) 上传原始文件 → 存入 MinIO（`user_{id}/documents/...`）→ 创建 Document(status=uploaded)
2) 生成 Markdown：
   - 非 PDF：同步生成 Markdown + chunks
   - PDF：异步任务（MinerU/magic-pdf → fallback → OCR）
3) 生成 chunks（写入 Postgres）→ 用户确认提交（status=confirmed）
4) 管理员审核：approve 触发索引；reject 写 reason
5) 索引：对 included chunks 生成 embedding → 写入 Milvus 分区（user_{id}）→ status=indexed

---

## 6. 查询链路（RAG）

1) 对 query 生成 embedding  
2) Milvus 检索 top_k 候选（默认只搜当前用户 partition）  
3) 可选 rerank（Xinference /v1/rerank）  
4) 拼接上下文 → 调用 LLM 生成答案（Ollama 或 OpenAI-compatible）  
5) 返回 answer + sources（document_id/chunk_index/relevance）  

---

## 7. 多租户隔离策略

### 7.1 Postgres（元数据/正文）
- 普通用户：所有查询过滤 `owner_id = current_user.id`
- 管理员：可跨用户查询（可按 owner_id 筛选）

### 7.2 MinIO（文件/Markdown）
- 采用 `user_{id}` 前缀隔离，便于备份、迁移与排障

### 7.3 Milvus（向量）
- 单 collection + per-user partition：`user_{id}`
- 普通用户查询只给自己的 partition；管理员可不指定 partition（全库）或指定某用户

---

## 8. 推理后端与离线部署策略

### 8.1 默认推荐组合（最小闭环）
- LLM：Ollama（`qwen2.5:32b`）
- Embedding：Ollama（`bge-large:latest`，dimension=1024）
- Rerank：Xinference（`bge-reranker-large`）

### 8.2 vLLM 环境
- 支持把 LLM provider 切到 vLLM（OpenAI-compatible `/v1/chat/completions`）
- 注意：RAG 检索仍需要 embedding；若无 Ollama，需要另外提供 embedding 方案（见 `OFFLINE_DEPLOYMENT.md` 的说明）

### 8.3 离线交付
外网 build + `docker save` → 内网 `docker load` + `docker compose -f ...offline... up -d`  
详见：`OFFLINE_DEPLOYMENT.md`

---

## 9. 可扩展点（内网定制常见需求）

- 审核规则/队列：调整哪些文档可见、何时可 confirm、approve 后是否自动索引
- OCR/解析策略：增加“仅 OCR / 仅 MinerU / 自动”策略与中间产物留存
- 推理 provider 扩展：增加更多 LLM/embedding/rerank 后端（建议同时补 `/diagnostics`）
- 检索增强：加入 BM25、混检、召回策略与阈值控制

