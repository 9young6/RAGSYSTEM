# RAG Knowledge Base System (Minimal)

This repository provides a minimal, Docker-Compose-friendly RAG knowledge base system:
- Upload PDF/DOCX
- Preview & confirm
- Admin review (approve/reject)
- Index to Milvus
- Query with Ollama (falls back to retrieved chunks if the model is not available)
- Chunk-level management (view/edit/include, optional re-embed)
- Optional rerank + acceptance/audit workflow

---

# 企业级文档管理 + RAG 知识库系统（最小可用版）

本项目按 `RAG-system-design.md` 的核心流程实现：**上传（PDF/DOCX）→ 解析预览 → 用户确认 → 管理员审核 → 索引到 Milvus → 查询**，并提供一个轻量前端页面与完整 FastAPI 接口。

## 目录
- [功能概览](#功能概览)
- [快速启动（Docker Compose）](#快速启动docker-compose)
- [访问入口](#访问入口)
- [使用流程](#使用流程)
- [API 速览](#api-速览)
- [配置说明](#配置说明)
- [测试脚本（Python SDK 风格）](#测试脚本python-sdk-风格)
- [常见问题](#常见问题)

## 功能概览
- 文档上传：支持 `PDF/DOCX/XLSX/CSV/MD/TXT/JSON`（MinIO 保存原文件 + Postgres 保存元数据/分块）
- 自动转 Markdown：`md/txt/json/csv/xlsx/docx` 直接生成；`pdf` 异步转换（失败可"开始/重试转换"）
- 文档确认：上传者确认后进入待审核队列
- 审核：管理员 approve/reject；approve 自动触发索引
- 向量检索：Milvus 保存向量（document_id/chunk_index/embedding）
- 问答：Ollama 生成（未下载模型时自动降级为"返回检索片段"）
- Chunk 管理：查看/编辑/新增/删除 chunk，支持勾选"入库"与（已入库文档）重建向量
- **Milvus 向量浏览**：3D 可视化向量空间分布，浏览所有 chunk 内容，支持搜索筛选和交互式探索
- 用户级设置：默认模型/top_k/temperature、推理后端与连通性测试
- 验收审查：上传报告→检索依据条款→生成固定格式"验收审查报告"
- 健康检查：`/api/v1/health` 检查 Postgres/Milvus/MinIO/Ollama（以及可选 Xinference）连通性
- 前端页面：上传 / 审核 / 查询 / Milvus 管理（深色主题，响应式设计）

## 快速启动（Docker Compose）
前置：Docker Desktop / Docker Compose v2

1) 启动
```bash
docker compose up -d --build
```

2) 验证健康检查
```bash
curl -s http://localhost:8001/api/v1/health
```

> 说明：本仓库默认把后端映射为 `8001:8000`（避免宿主机 `8000` 端口冲突）。如需改回 8000，请改 `docker-compose.yml` 中 `backend.ports`。

## 访问入口
- **主应用前端**：`http://localhost:3000` （上传/审核/查询/设置）
- **Milvus 向量浏览**：`http://localhost:3000/milvus.html` （3D 可视化，Chunk 浏览）
- **Swagger 文档**：`http://localhost:8001/docs`
- **ReDoc**：`http://localhost:8001/redoc`

默认情况下仅暴露 **前端/后端** 端口；如需在宿主机访问 MinIO 控制台/Milvus/Postgres 等，请自行在 `docker-compose.yml` 为对应服务补充 `ports` 映射。

默认账号（首次启动会自动初始化）：
- 管理员：见 `.env`（`ADMIN_USERNAME` / `ADMIN_PASSWORD`）

注册：
- 前端支持注册普通用户（默认角色 `user`，不可进行“内容审核”）
- API：`POST /api/v1/auth/register`

## 使用流程
0) 注册（可选）：在前端点“注册”创建普通用户账号（或使用管理员账号，见 `.env`）
1) 登录（前端右上角/或 API `/auth/login`）
2) 上传 PDF/DOCX（返回 `document_id` + `preview`）
3) 确认文档：`/documents/confirm/{id}`（状态变为 `confirmed`）
4) 管理员审核：
   - 通过：`/review/approve/{id}`（自动索引，最终状态 `indexed`）
   - 拒绝：`/review/reject/{id}`（状态 `rejected`）
5) 查询：`/query`

状态流转：
`uploaded -> confirmed -> indexed`（通过并索引）或 `uploaded -> confirmed -> rejected`
> 被拒绝（`rejected`）后，用户可在“我的知识库”查看拒绝原因并点击“重新提交”再次进入审核流程。

## API 速览
接口基路径：`/api/v1`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/login` | 登录获取 JWT |
| POST | `/auth/register` | 注册普通用户并返回 JWT |
| POST | `/documents/upload` | 上传文档（multipart） |
| POST | `/documents/confirm/{id}` | 确认文档进入审核 |
| GET | `/documents/{id}` | 查询文档状态 |
| GET | `/review/pending` | 管理员：待审核列表 |
| POST | `/review/approve/{id}` | 管理员：通过并索引 |
| POST | `/review/reject/{id}` | 管理员：拒绝 |
| POST | `/query` | RAG 查询 |
| GET | `/health` | 依赖健康检查 |

## 配置说明
配置文件：`.env`（模板：`.env.example`）

重点参数：
- `DATABASE_URL`：Postgres 连接串（容器内默认 `postgres` 主机名）
- `MILVUS_HOST/MILVUS_PORT`：Milvus 连接
- `MINIO_*`：MinIO 连接与 bucket
- `OLLAMA_BASE_URL/OLLAMA_MODEL`：Ollama 模型与服务地址
- `OLLAMA_EMBEDDING_MODEL`：Ollama embedding 模型（例如 `bge-m3:latest`）
- `EMBEDDING_PROVIDER`：
  - `hash`（默认）：零依赖快速跑通，但检索质量不保证（适合验收链路）
  - `ollama`：使用 Ollama `/api/embeddings`（需拉取 embedding 模型，例如 `bge-m3:latest`，并设置 `EMBEDDING_DIMENSION`）
  - `sentence_transformers`：本地向量模型（需安装可选依赖，见 `backend/requirements-optional.txt`）
- 可选推理后端（OpenAI 兼容）：`VLLM_BASE_URL` / `XINFERENCE_BASE_URL`（见 `.env.example`）

## 测试脚本（Python SDK 风格）
脚本：`scripts/sdk_smoke_test.py`

推荐在容器内运行（依赖已齐全）：
```bash
docker compose exec backend python /scripts/sdk_smoke_test.py --api-url http://localhost:8000/api/v1 --with-pdf --with-reject
```

也可以在宿主机运行（需要本机安装 `requests` + `python-docx`）：
```bash
python scripts/sdk_smoke_test.py --api-url http://localhost:8001/api/v1 --with-pdf --with-reject
```

覆盖内容：health、登录、DOCX/PDF 上传、确认、审核通过触发索引、拒绝、查询。
新增覆盖：chunk CRUD+向量同步、（可选）rerank 不阻断、验收审查报告生成。

## 常见问题
1) 端口冲突
- 本仓库默认后端端口为 `8001`；如需修改，编辑 `docker-compose.yml` 中 `backend.ports`。

2) Ollama 没有模型导致回答为空/降级
- 查看已安装模型：
  ```bash
  docker compose exec ollama ollama list
  ```
- 拉取模型（示例，按需选择）：
  ```bash
  docker compose exec ollama ollama pull qwen2.5:32b
  ```
  没有安装模型时，查询接口会返回“LLM 模型不可用…”并附带检索片段用于排障。

3) 需要更高质量的向量检索
- 将 `.env` 的 `EMBEDDING_PROVIDER` 从 `hash` 切到 `ollama` 或 `sentence_transformers`，并安装 `backend/requirements-optional.txt` 中依赖/拉取 embedding 模型。

4) PDF 解析不到内容
- 如果是扫描件/图片 PDF，本项目会在文本提取很少时自动尝试 OCR（Tesseract），并把 OCR 结果写入 Markdown（见 `.env.example` 的 `OCR_*` 配置）。
