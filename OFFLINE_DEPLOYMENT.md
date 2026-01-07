# 离线/内网部署与维护说明（镜像打包）

本项目支持“外网构建镜像 → 导出 tar → 内网导入运行”的交付方式；内网环境无需访问外网，也不会拉取任何新镜像。

> 运行验收与调试建议见：`PROJECT_RUNBOOK.md`。

---

## 目录
- [1. 交付物与目录](#1-交付物与目录)
- [2. 外网机器：构建与导出](#2-外网机器构建与导出)
- [3. 内网机器：导入与启动](#3-内网机器导入与启动)
- [4. 关键配置（.env）](#4-关键配置env)
- [5. 内网验收（不依赖拉新镜像）](#5-内网验收不依赖拉新镜像)
- [6. 增量更新（推荐流程）](#6-增量更新推荐流程)

---

## 1. 交付物与目录

- `docker-compose.yml`：默认开发/可用配置（含 build）。
- `docker-compose.offline.yml`：离线覆盖配置（`pull_policy: never` + 去掉代码挂载、关闭 `--reload`）。
- `scripts/offline/export-images.ps1`：外网导出镜像 tar 包。
- `scripts/offline/import-images.ps1`：内网导入镜像 tar 包。
- `offline/images/`：导出的镜像文件目录（运行导出脚本后生成）。

---

## 2. 外网机器：构建与导出

前置条件：
- 外网机器可访问镜像源/包源（用于首次 build 的 apt/pip 依赖下载）
- 已安装 Docker Desktop / Docker Engine + Docker Compose v2

1) 首次建议完整跑通一次：

`docker compose up -d --build`

2) 后续只构建业务镜像（推荐，避免不必要的 pull）：

`docker compose build --pull=false backend frontend`

> 注意：`celery_worker` 复用 `ragsystem_backend:local` 镜像，不需要单独 build。

3) 导出镜像到 tar（只导出本地已有镜像，不会再下载）：

`powershell -ExecutionPolicy Bypass -File scripts/offline/export-images.ps1`

导出结果：
- `offline/images/*.tar`：每个镜像一个 tar
- `offline/images/manifest.json`：镜像清单（含 sha256）

4) 拷贝到内网：
- 项目目录（至少：`docker-compose.yml`、`docker-compose.offline.yml`、`.env`/`.env.example`、`scripts/`、`offline/images/`）

---

## 3. 内网机器：导入与启动

前置条件：内网机器已安装 Docker / Docker Compose（无需外网）。

1) 导入镜像：

`powershell -ExecutionPolicy Bypass -File scripts/offline/import-images.ps1`

2) 准备环境变量：
- 复制 `.env.example` 为 `.env` 并按需修改（见下一节）。
- **推理后端默认在容器外部**（不强制随项目打包）：Ollama / Xinference / vLLM 均可部署在内网任意主机。

3) 离线启动（强制不拉镜像）：

`docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d`

4) 访问：
- 前端：`http://<内网机器IP>:3000`
- 后端 API：`http://<内网机器IP>:8001/api/v1`

默认管理员账号（首次启动自动创建）：
- 见 `.env`（`ADMIN_USERNAME` / `ADMIN_PASSWORD`）

---

## 4. 关键配置（.env）

### 4.1 基础依赖（必填/常用）
- `OLLAMA_BASE_URL`：Ollama 地址（Docker Desktop 常用 `http://host.docker.internal:11434`；Linux 内网请改为宿主机 IP/域名）
- `OLLAMA_MODEL`：默认对话模型（例如 `qwen2.5:32b`）
- `OLLAMA_EMBEDDING_MODEL`：默认嵌入模型（例如 `bge-large:latest`）
- `EMBEDDING_PROVIDER=ollama` + `EMBEDDING_DIMENSION=1024`：必须与 embedding 输出维度一致

### 4.2 Rerank（推荐）
- `XINFERENCE_BASE_URL`：Xinference 地址（用于 rerank 与可选的 OpenAI-compatible LLM）
- 运行时在“设置”页启用 rerank，并选择模型（推荐：`bge-reranker-large`）

### 4.3 vLLM 环境（常见内网部署）
本项目支持把 **LLM provider 切到 vLLM**（OpenAI-compatible）：
- 配置：`VLLM_BASE_URL` / `VLLM_API_KEY`（如需要）
- 使用：查询时 `provider=vllm`，并指定 `model`（或在用户设置里保存默认）

重要：**RAG 检索必需 embedding**。若内网“只有 vLLM、没有 Ollama”，请在交付前明确 embedding 方案：
- 方案 A（最小改动）：仍提供一个 embedding 服务（Ollama 或其他），`EMBEDDING_PROVIDER` 指向它
- 方案 B（后端本地 embedding）：启用 `sentence_transformers`（需要在 `backend/requirements.txt` 增加依赖，并离线预置模型缓存）

### 4.4 MinerU / OCR（PDF 转换）
- `MINERU_USE_MAGIC_PDF=true`：默认启用 MinerU/magic-pdf（失败自动降级到常规解析；见 worker 日志）
- `OCR_ENABLED=true`：当 PDF 文本提取很少时自动尝试 OCR（其余参数见 `.env.example`）

注意：
- `EMBEDDING_DIMENSION` / `MILVUS_COLLECTION` 在已有数据入库后不建议随意修改；需要变更时应新建 collection 并全量重建向量。

---

## 5. 内网验收（不依赖拉新镜像）

推荐用冒烟脚本一次性验证闭环（避免手工接口遗漏）：

`docker compose exec backend python /scripts/sdk_smoke_test.py --api-url http://localhost:8000/api/v1 --auto-register --model qwen2.5:32b`

同时建议关注日志：
- `docker compose logs --tail 200 backend`
- `docker compose logs --tail 200 celery_worker`

---

## 6. 增量更新（推荐流程）

目标：**只改哪里，就只更新哪里**，减少导出/导入体积与风险。

### 6.1 只更新后端/前端镜像
外网机器：
1) 改代码
2) 构建：
   - `docker compose build --pull=false backend` 或 `docker compose build --pull=false frontend`
3) 只导出变更镜像：
   - `docker save -o offline/images/ragsystem_backend_local.tar ragsystem_backend:local`
   - `docker save -o offline/images/ragsystem_frontend_local.tar ragsystem_frontend:local`

内网机器：
1) 导入：
   - `docker load -i offline/images/ragsystem_backend_local.tar`
   - `docker load -i offline/images/ragsystem_frontend_local.tar`
2) 重启：
   - `docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d`

> `celery_worker` 复用后端镜像，所以更新后端镜像即可同时更新 worker。

### 6.2 内网新增 Python 依赖（无外网 pip）
推荐方式：外网把依赖打进镜像再交付（可追溯/可复现）。

应急方式（不推荐长期使用）：在内网把 whl 装进运行容器后 `docker commit` 固化为新镜像（会带来不可追溯成本）。

