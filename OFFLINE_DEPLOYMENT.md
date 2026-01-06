# 离线/内网部署与维护说明（镜像打包）

本项目支持“外网打包镜像 → 内网导入运行”的交付方式，内网环境无需再拉取任何新镜像。

## 1. 目录与文件

- `docker-compose.yml`：默认开发/可用配置（含 build）。
- `docker-compose.offline.yml`：离线覆盖配置（`pull_policy: never` + 去掉后端代码挂载、关闭 `--reload`）。
- `scripts/offline/export-images.ps1`：在外网机器导出镜像 tar 包。
- `scripts/offline/import-images.ps1`：在内网机器导入镜像 tar 包。
- `offline/images/`：导出的镜像文件目录（运行导出脚本后生成）。

## 2. 外网机器：构建 + 打包镜像

前置条件：外网机器能访问镜像源/包源；已安装 Docker Desktop / Docker Engine。

1) 启动并验证服务（建议先跑通一次）：

`docker compose up -d --build`

2) 只构建业务镜像（后续增量维护时也推荐这么做）：

`docker compose build --pull=false backend frontend`

> 注意：`celery_worker` 复用 `ragsystem_backend:local` 镜像，不需要单独 build。

3) 导出镜像到 tar（不会再下载，纯导出本地已有镜像）：

`powershell -ExecutionPolicy Bypass -File scripts/offline/export-images.ps1`

导出结果：
- `offline/images/*.tar`：每个镜像一个 tar
- `offline/images/manifest.json`：镜像清单（含 sha256）

4) 将以下内容拷贝到内网机器：
- 项目目录（至少需要：`docker-compose.yml`、`docker-compose.offline.yml`、`.env`/`.env.example`）
- `offline/images/` 整个目录

## 3. 内网机器：导入镜像 + 启动

前置条件：内网机器已安装 Docker / Docker Compose（不需要能访问外网）。

1) 导入镜像：

`powershell -ExecutionPolicy Bypass -File scripts/offline/import-images.ps1`

2) 准备环境变量：

- 复制 `.env.example` 为 `.env` 并按需修改。
- 本项目默认 **Ollama 在容器外部**（不打包 `ollama/ollama` 镜像），请设置 `OLLAMA_BASE_URL` 为可访问地址。
- 请确保外部 Ollama 已准备好模型：
  - LLM：例如 `qwen3:latest`
  - Embedding：例如 `bge-m3:latest`

3) 启动（强制离线策略，不会拉取任何镜像）：

`docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d`

4) 访问：
- 前端：`http://<内网机器IP>:3000`
- 后端 API：`http://<内网机器IP>:8001/api/v1`

默认管理员账号（首次启动自动创建）：
- 见 `.env`（`ADMIN_USERNAME` / `ADMIN_PASSWORD`）

## 3.1 关键配置说明（.env）

必填/常用：
- `OLLAMA_BASE_URL`：外部 Ollama 地址（Docker Desktop 可用 `http://host.docker.internal:11434`，Linux 内网请改为宿主机 IP）
- `OLLAMA_MODEL`：默认对话模型（例如 `qwen3:latest`）
- `OLLAMA_EMBEDDING_MODEL`：默认嵌入模型（例如 `bge-m3:latest`）
- `EMBEDDING_PROVIDER=ollama` + `EMBEDDING_DIMENSION=1024`：与 Milvus collection 维度一致

可选（OpenAI 兼容推理后端）：
- `VLLM_BASE_URL` / `VLLM_API_KEY`：用于 `vllm` provider（`/v1/chat/completions`）
- `XINFERENCE_BASE_URL` / `XINFERENCE_API_KEY`：用于 `xinference` provider（`/v1/chat/completions`），以及可选 Rerank（`/v1/rerank`）

注意：`EMBEDDING_DIMENSION` / `MILVUS_COLLECTION` 一旦有数据入库后不建议随意修改；需要变更时建议新建 collection 并重建向量。

## 3.2 功能测试（不依赖拉新镜像）

下面示例以 Windows PowerShell 为例（把 `<IP>` 替换为内网机器 IP）：

1) 健康检查：

`Invoke-WebRequest -UseBasicParsing http://<IP>:8001/api/v1/health | Select-Object -ExpandProperty Content`

2) 登录拿 token：

`$token = (Invoke-WebRequest -UseBasicParsing -Method Post http://<IP>:8001/api/v1/auth/login -ContentType 'application/json' -Body '{\"username\":\"<ADMIN_USERNAME>\",\"password\":\"<ADMIN_PASSWORD>\"}').Content | ConvertFrom-Json | Select-Object -ExpandProperty access_token`

3) 上传文件（示例：txt，上传后会自动生成 Markdown + chunks）：

`Invoke-WebRequest -UseBasicParsing -Method Post http://<IP>:8001/api/v1/documents/upload -Headers @{Authorization=\"Bearer $token\"} -Form @{file=Get-Item .\\demo.txt} | Select-Object -ExpandProperty Content`

4) 查看 Markdown 状态 / 触发重试转换：

- `GET /api/v1/documents/{id}/markdown/status`
- `POST /api/v1/documents/{id}/markdown/convert`

5) Chunk 查看与编辑（SQL 为准，Milvus 为索引）：

- `GET /api/v1/documents/{id}/chunks`
- `PATCH /api/v1/documents/{id}/chunks/{chunk_id}`（支持修改 `content` 与 `included`）
- `POST /api/v1/documents/{id}/chunks/reembed`（已入库文档重建向量）

6) 查询（可选 rerank）：

- 普通用户：`POST /api/v1/query`
- 管理员全库：`POST /api/v1/query/admin`
- 可选参数：`provider=ollama|vllm|xinference`，以及 `rerank=true&rerank_provider=xinference&rerank_model=...`

7) 验收审查（生成固定格式报告）：

- `POST /api/v1/acceptance/run`
  - `scope=self|user|all`（`user/all` 需要管理员）
  - 返回 `report_markdown`（可直接保存为 .md）

## 4. 内网“不能拉新镜像”的注意事项

- 离线启动必须带 `docker-compose.offline.yml`，它把所有服务设置为 `pull_policy: never`。
- 如果启动时报 “image not found”，说明你没有导入该镜像 tar（或导入到了不同的 Docker Context）。

## 5. 后期维护：如何增量更新（推荐流程）

### 5.1 只更新后端/前端代码（推荐外网构建 → 内网导入）

外网机器：
1) 更新代码
2) `docker compose build backend`（或 `docker compose build frontend`）
3) 重新导出镜像（只会 `docker save`，不需要重新 pull）：
   - 你可以直接再次运行 `scripts/offline/export-images.ps1`（会覆盖对应 tar）。

内网机器：
1) `scripts/offline/import-images.ps1`
2) `docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d`

### 5.2 内网新增 Python 依赖（whl）怎么做

内网无法访问 PyPI 时，不要在运行中的容器里“临时 pip install”作为长期方案（容器重建会丢）。

推荐两种方式：

**方式 A（推荐）：外网构建包含依赖的新镜像 → 内网导入**
- 外网修改 `backend/requirements.txt`（或你的依赖文件）
- 外网执行 `docker compose build backend`
- 外网导出镜像 tar，内网导入并重启

**方式 B（应急）：内网把 whl 装进运行中的容器，再固化为新镜像**
1) 拷贝 whl 到容器：
   - `docker cp some_pkg.whl kb_backend:/tmp/some_pkg.whl`
2) 安装：
   - `docker exec -it kb_backend pip install /tmp/some_pkg.whl`
3) 固化成新镜像：
   - `docker commit kb_backend ragsystem_backend:patched`
4) 导出/内网备份：
   - `docker save -o offline/images/ragsystem_backend_patched.tar ragsystem_backend:patched`

> 方式 B 适合临时修复；长期仍建议回到方式 A（可追溯、可复现）。

### 5.3 只导出/导入单个镜像（节省流量）

如果你只改了前端或后端，不必每次都导出全部镜像：

- 外网机器导出单个镜像：
  - `docker save -o offline/images/ragsystem_frontend_local.tar ragsystem_frontend:local`
  - `docker save -o offline/images/ragsystem_backend_local.tar ragsystem_backend:local`
- 内网机器导入单个镜像：
  - `docker load -i offline/images/ragsystem_frontend_local.tar`
  - `docker load -i offline/images/ragsystem_backend_local.tar`

导入后执行：`docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d`

## 6. 数据与持久化

本项目使用 Docker volumes 持久化数据（Postgres/Milvus/MinIO/Redis/MinerU 模型缓存）。
迁移到新内网机器时，这些 volumes 默认是空的；如需迁移历史数据，需要额外导出/导入 volumes（不在本文件范围内）。
