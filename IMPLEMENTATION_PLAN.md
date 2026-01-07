# 实施与迭代计划（与当前代码一致）

本文档用于给“交付内网 + 长期维护”的团队提供一个可执行的迭代清单：哪些能力已经闭环、上线前怎么验收、后续常见增强点从哪里做起。

> 运行/部署命令请看：`PROJECT_RUNBOOK.md`；离线交付请看：`OFFLINE_DEPLOYMENT.md`；代码入口与定制点请看：`ARCHITECTURE.md`。

---

## 1. 当前能力（已实现）

### 1.1 多租户隔离
- Postgres：`Document.owner_id` 作为归属与权限过滤关键字段。
- MinIO：对象路径按 `user_{id}/...` 组织（原始文件/Markdown 分开）。
- Milvus：单 collection + per-user partition（`user_{id}`）隔离检索空间。

### 1.2 文档工作流闭环
- 上传：`POST /documents/upload`（写入 MinIO + 建 Document）
- Markdown：
  - 非 PDF：同步生成 Markdown + chunks
  - PDF：Celery 异步 MinerU/magic-pdf（失败自动降级 + 可选 OCR）
- 用户确认提交：`POST /documents/confirm/{id}`（仅允许 markdown_ready）
- 管理员审核：`GET /review/pending`、`POST /review/approve/{id}`、`POST /review/reject/{id}`
- 入库：approve 后触发索引写入 Milvus（仅 included=true 的 chunk）
- 查询：`POST /query`（用户库）/ `POST /query/admin`（管理员跨库）

### 1.3 Chunk 可编辑（入库前/入库后）
- CRUD：`/documents/{id}/chunks*`
- `included` 控制是否参与入库
- 已入库文档支持重建向量：
  - 对单文档 chunks：`POST /documents/{id}/chunks/reembed`
  - 管理员批量：`POST /admin/reindex`

### 1.4 推理后端与诊断
- LLM：Ollama / OpenAI-compatible（vLLM、Xinference）
- Embedding：Ollama（默认）/ hash（演示）/ sentence-transformers（代码支持，若要启用需安装依赖）
- Rerank：Xinference（`/v1/rerank`）
- 连通性诊断：`/diagnostics/*`

---

## 2. 上线前验收（推荐必做）

### 2.1 冒烟脚本（推荐）
在容器内执行（依赖齐全）：
- `docker compose exec backend python /scripts/sdk_smoke_test.py --api-url http://localhost:8000/api/v1 --auto-register --model qwen2.5:32b`

覆盖链路：
- 注册/登录 → 上传 → 等待 markdown_ready → 确认提交 → 管理员审批索引 → 查询命中 sources
- Chunk CRUD + included + reembed
- rerank（未配置也不阻断）
- 验收审查报告生成

### 2.2 关键配置核对（.env）
- `EMBEDDING_PROVIDER` 与 embedding 模型输出维度匹配（`EMBEDDING_DIMENSION`）
- `MILVUS_COLLECTION` 在“已有数据”后不随意变更（需要重建向量）
- `OLLAMA_BASE_URL` / `XINFERENCE_BASE_URL` / `VLLM_BASE_URL` 在容器内可访问（常见：`host.docker.internal`）

---

## 3. 迭代建议（内网常见增强项）

按优先级给出建议方向（不强制）：

### P0：稳定性与可观测性
- 为关键链路（上传、转换、索引、查询）补充更聚合的日志字段（doc_id/owner_id/task_id）。
- 在前端增加“错误详情/建议操作”的展示（后端已返回 markdown_error、诊断 error）。

### P1：纯 vLLM 环境适配（无 Ollama）
当前最小可行方案：
- LLM 使用 vLLM（查询时 provider=vllm）
- embedding 仍需一个 embedding 提供方：Ollama 或在后端启用 sentence-transformers（需在 `backend/requirements.txt` 增加依赖并离线预置模型）

如需要“embedding 也走 OpenAI-compatible”（vLLM/Xinference），建议后续在 `EmbeddingService` 增加 provider 支持，并同步扩展 `/diagnostics` 测试。

### P2：OCR/解析能力增强
- 对扫描 PDF：OCR 结果落地为 Markdown（当前已支持），可进一步：
  - 保存中间产物（图片/页面文本）用于追溯
  - 增加“仅 OCR / 仅 MinerU / 自动”策略开关（UI + 任务参数）

### P2：审核流程扩展
- 增加更多审核动作（例如 request_changes/escalate）
- 对接外部审批系统（Webhook/MQ），以 `ReviewAction` 为审计入口

---

## 4. 变更流程建议（长期维护）

1) 先改文档（说明目的、影响范围、如何验证），再改代码  
2) 改后端：优先补齐 `scripts/sdk_smoke_test.py` 覆盖用例或加小范围自测  
3) 构建镜像并离线交付：参考 `OFFLINE_DEPLOYMENT.md` 的 export/import 流程  

