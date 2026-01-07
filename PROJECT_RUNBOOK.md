# 项目运行手册（部署 / 调试 / 测试 / 维护）

本文档面向“交付到内网并长期维护”的场景，覆盖：
- 如何启动（开发态 / 离线态）
- 如何按功能验证闭环（前端 + API）
- 如何在**后端镜像环境**里调试与定位问题
- 如何最小化重打包与离线增量更新

相关文档：
- 架构与定制入口：`ARCHITECTURE.md`
- 离线交付与镜像打包：`OFFLINE_DEPLOYMENT.md`

---

## 1. 组成与端口

### 1.1 服务组成（docker compose）
- `frontend`：静态前端（`http://localhost:3000`）
- `backend`：FastAPI（宿主机 `8001 -> 容器 8000`）
- `celery_worker`：异步任务（PDF 转 Markdown、OCR 等）
- `postgres`：元数据与 chunk（Docker volume 持久化）
- `milvus + etcd`：向量检索（Docker volume 持久化）
- `minio`：对象存储（Docker volume 持久化）
- `redis`：Celery broker/缓存

说明：`backend` 与 `celery_worker` 复用同一个后端镜像（`ragsystem_backend:local`），只是启动命令不同（API vs worker）。

### 1.2 访问入口
- 前端：`http://localhost:3000`
- 后端 API Base：`http://localhost:8001/api/v1`
- Swagger：`http://localhost:8001/docs`

### 1.3 推理后端（默认在容器外部）
本项目默认不强制打包推理后端镜像（Ollama/Xinference/vLLM 可部署在内网任意主机），后端通过 `.env` 访问：
- `OLLAMA_BASE_URL`：LLM + embedding（推荐：LLM `qwen2.5:32b`，embedding `bge-large:latest`）
- `XINFERENCE_BASE_URL`：rerank（推荐：`bge-reranker-large`），也可作为 OpenAI-compatible LLM
- `VLLM_BASE_URL`：可选 OpenAI-compatible LLM（适合“内网统一 vLLM”）

---

## 2. 快速启动（开发态）

### 2.1 前置条件
- Docker Desktop / Docker Engine + Docker Compose v2
- 推理后端至少准备好一种：
  - **推荐最小闭环**：Ollama（LLM + embedding）
  - **可选增强**：Xinference（rerank），vLLM（LLM）

### 2.2 配置（.env）
1) 复制 `.env.example` 为 `.env`
2) 至少确认：
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL=qwen2.5:32b`
- `OLLAMA_EMBEDDING_MODEL=bge-large:latest`
- `EMBEDDING_PROVIDER=ollama`
- `EMBEDDING_DIMENSION=1024`（需与 embedding 输出一致）
- （可选）`XINFERENCE_BASE_URL`（用于 rerank）

### 2.3 启动

`docker compose up -d --build`

### 2.4 健康检查

`Invoke-WebRequest -UseBasicParsing http://localhost:8001/api/v1/health | Select-Object -ExpandProperty Content`

---

## 3. 离线/内网启动（不拉新镜像）

离线交付与增量更新细节请看：`OFFLINE_DEPLOYMENT.md`。这里给出摘要：

`docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d`

---

## 4. 功能验证清单（建议按顺序）

### 4.1 登录/注册
前端：`/login.html` 注册普通用户或登录管理员。

验收点：
- 登录成功后能进入 `app.html`，右上角展示 username/role。

### 4.2 上传与转换（Markdown）
前端：上传 `pdf/docx/xlsx/csv/md/txt/json`。

验收点：
- `md/txt/json/csv/xlsx/docx` 通常很快到 `markdown_ready`
- `pdf` 进入 `processing`，完成后到 `markdown_ready`（失败会显示 `markdown_error`）
- 扫描 PDF：如开启 `OCR_ENABLED=true`，文本过少时会自动尝试 OCR

### 4.3 Markdown 下载/上传与确认提交
前端：在上传页：
- 下载 Markdown → 修改 → 上传 Markdown
- 点击“提交审核”（确认提交）

验收点：
- `confirm` 仅在 `markdown_ready` 时允许（避免“待转换”进入审核队列）

### 4.4 管理员审核与入库
前端：管理员进入“文档审核”：
- 待审核列表应只包含 `confirmed + markdown_ready`
- 通过（approve）后，文档应进入 `indexed`
- 拒绝（reject）后，用户端文档列表应可看到拒绝原因并可重新提交

### 4.5 Chunk 管理（编辑与 included）
前端：文档列表打开“Chunk 管理”：
- 可编辑 chunk 内容
- 可勾选 included（控制是否入库）
- 已入库文档可“重建向量”

验收点：
- 修改 chunk 后重建向量，查询能反映最新内容

### 4.6 查询（RAG + 可选 rerank）
前端：知识库查询，输入问题。

验收点：
- 返回 answer + sources（document_id/chunk_index）
- 启用 rerank 时（Xinference 配置正确），sources 顺序会调整；未配置也不应报错（自动跳过）
- 如使用 vLLM：在设置或查询参数里选择 provider=vllm 并设置 model

### 4.7 设置与连通性测试
前端：设置页：
- 保存用户默认 provider/model/top_k/temperature/rerank
- 运行连通性测试（LLM / rerank / Ollama embedding）

验收点：
- 失败时能给出明确 error（便于内网排障）

### 4.8 冒烟测试脚本（推荐一次性验证）
在容器内运行（避免宿主机 Python 依赖差异）：

`docker compose exec backend python /scripts/sdk_smoke_test.py --api-url http://localhost:8000/api/v1 --auto-register --model qwen2.5:32b`

---

## 5. 后端镜像环境调试（重点）

### 5.1 查看日志（定位问题第一步）
- API：`docker compose logs --tail 200 backend`
- 异步任务：`docker compose logs --tail 200 celery_worker`
- 依赖：`docker compose logs --tail 200 minio` / `milvus` / `postgres`

### 5.2 进入容器排查
进入后端容器：
- `docker compose exec backend sh`

常用排查：
- 读取当前环境变量：`env | sort`
- 试连 Ollama：`python -c "import requests,os;print(requests.get(os.environ['OLLAMA_BASE_URL'].rstrip('/')+'/api/tags').status_code)"`
- 试连 Xinference rerank：`python -c "import requests,os;print(requests.post(os.environ['XINFERENCE_BASE_URL'].rstrip('/')+'/v1/rerank',json={'model':'bge-reranker-large','query':'ping','documents':['a','b']}).status_code)"`

### 5.3 用后端诊断接口快速确认连通性
- `POST /api/v1/diagnostics/ollama`
- `POST /api/v1/diagnostics/inference`
- `POST /api/v1/diagnostics/rerank`

### 5.4 向量丢失/迁移后的重建
Milvus volumes 清空或迁移后，常见现象是“文档是 indexed 但检索不到”。

解决：
- `POST /api/v1/admin/reindex`（可按 document_ids / owner_id 选择范围）

---

## 6. 修改后如何最小化重打包与离线更新

目标：只改哪里，就只重建/导出哪里（避免重复下载、节省流量）。

### 6.1 改后端（FastAPI / Celery）
外网机器：
- `docker compose build --pull=false backend`
- `docker save -o offline/images/ragsystem_backend_local.tar ragsystem_backend:local`

内网机器：
- `docker load -i offline/images/ragsystem_backend_local.tar`
- `docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d`

> `celery_worker` 复用后端镜像，所以更新后端镜像即可同时更新 worker。

### 6.2 改前端（静态页面）
外网机器：
- `docker compose build --pull=false frontend`
- `docker save -o offline/images/ragsystem_frontend_local.tar ragsystem_frontend:local`

内网机器：
- `docker load -i offline/images/ragsystem_frontend_local.tar`
- `docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d`

