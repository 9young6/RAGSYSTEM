# 项目使用说明（部署 / 测试 / 维护 / 离线交付）

本说明面向“交付到内网并长期维护”的场景，覆盖：
- 如何部署（外网/内网/离线）
- 如何按功能逐项测试（前端 + API）
- 修改单个功能后如何最小化重打包镜像、重新导出并在内网更新

> 重要：本项目默认 **Ollama 在容器外部**（不打包 `ollama/ollama` 镜像）。容器通过 `.env` 的 `OLLAMA_BASE_URL` 访问宿主机/内网的 Ollama 服务。

## 目录
- [1. 组成与端口](#1-组成与端口)
- [2. 快速部署（外网机器）](#2-快速部署外网机器)
- [3. 离线/内网部署（不拉新镜像）](#3-离线内网部署不拉新镜像)
- [4. 单功能测试清单](#4-单功能测试清单)
- [5. 冒烟测试（推荐）](#5-冒烟测试推荐)
- [6. 修改功能后的维护与重打包](#6-修改功能后的维护与重打包)
- [7. 常见问题排查](#7-常见问题排查)
- [8. 数据与备份提示](#8-数据与备份提示)

---

## 1. 组成与端口

### 1.1 服务组成（docker compose）
- `frontend`：静态前端（`http://localhost:3000`）
- `backend`：FastAPI（宿主机 `8001 -> 容器 8000`）
- `celery_worker`：异步任务（文档转换/切分等）
- `postgres`：元数据与 chunk（Docker volume 持久化）
- `milvus + etcd`：向量检索（Docker volume 持久化）
- `minio`：文件存储（Docker volume 持久化）
- `redis`：Celery broker/缓存

> 为什么会看到两个容器用同一个后端镜像：`backend` 与 `celery_worker` 都复用 `ragsystem_backend:local`，只是启动命令不同（API vs worker）。

### 1.2 访问入口
- 前端：`http://localhost:3000`
- 后端 API Base：`http://localhost:8001/api/v1`
- 后端 Swagger：`http://localhost:8001/docs`

### 1.3 管理员账号
管理员账号密码由 `.env` 决定（`ADMIN_USERNAME` / `ADMIN_PASSWORD`）。
- 前端不会展示明文密码
- 文档里也不写死密码（避免泄露）

---

## 2. 快速部署（外网机器）

### 2.1 前置条件
- Docker Desktop / Docker Engine + Docker Compose v2
- 外部 Ollama 已安装并可访问（Windows Docker Desktop 通常可用 `http://host.docker.internal:11434`）
- 需先在 Ollama 里准备模型（示例）：
  - LLM：`qwen2.5:32b`
  - Embedding：`bge-large:latest`
  - （可选）Rerank：`bge-reranker-large`（通过 Xinference 提供）

### 2.2 配置
1) 复制 `.env.example` 为 `.env`，至少确认：
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `OLLAMA_EMBEDDING_MODEL`
- `EMBEDDING_PROVIDER=ollama`
- `EMBEDDING_DIMENSION=1024`（需与 embedding 模型输出维度一致）
- （可选）Rerank：`XINFERENCE_BASE_URL` + 设置页启用 `bge-reranker-large`
- （可选）扫描 PDF OCR：`OCR_ENABLED=true`（其余参数见 `.env.example`）

2) 启动：
- `docker compose up -d --build`

3) 健康检查：
- `Invoke-WebRequest -UseBasicParsing http://localhost:8001/api/v1/health | Select-Object -ExpandProperty Content`

---

## 3. 离线/内网部署（不拉新镜像）

离线交付与增量更新的详细步骤已在 `OFFLINE_DEPLOYMENT.md` 中给出；这里给出“项目级”摘要：

### 3.1 外网机器：构建 + 导出镜像
1) 构建业务镜像（避免重复 pull）：
- `docker compose build --pull=false backend frontend`

2) 导出镜像（生成 `offline/images/*.tar` + `manifest.json`）：
- `powershell -ExecutionPolicy Bypass -File scripts/offline/export-images.ps1`

3) 把整个项目目录（含 `offline/images/`）拷贝到内网。

### 3.2 内网机器：导入 + 离线启动
1) 导入镜像：
- `powershell -ExecutionPolicy Bypass -File scripts/offline/import-images.ps1`

2) 准备 `.env`（重点是 `OLLAMA_BASE_URL` 指向内网可访问的外部 Ollama）。

3) 离线启动（强制不拉镜像）：
- `docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d`

---

## 4. 单功能测试清单

下面给出“每个功能一条可验证闭环”。建议优先用前端操作；若需要可用 API 方式复现。

### 4.1 登录 / 注册
前端：
- 打开 `http://localhost:3000/login.html`
- 注册普通用户（或用管理员登录）

API（PowerShell 示例）：
- `Invoke-WebRequest -UseBasicParsing -Method Post http://localhost:8001/api/v1/auth/login -ContentType 'application/json' -Body '{\"username\":\"<USERNAME>\",\"password\":\"<PASSWORD>\"}'`

验收点：
- 返回 `access_token`

### 4.2 文档上传（多格式）与自动转 Markdown
前端：
- 进入“上传文件”
- 上传 `pdf/docx/xlsx/csv/md/txt/json`
- 查看 Markdown 状态（自动轮询），失败可点“开始/重试转换”

验收点：
- `md/txt/json/csv/xlsx/docx` 通常会很快到 `markdown_ready`
- `pdf` 会进入 `processing`，完成后到 `markdown_ready`（失败会显示失败原因）
- 若 PDF 为扫描件且几乎提取不到文本：会尝试 OCR，并把 OCR 结果写入 Markdown（见 `.env.example` 的 OCR 配置）

### 4.3 查看与编辑 chunks（RAGFlow 风格）
前端：
- “我的知识库”列表里点某文档的 `Chunks`
- 即使 Markdown 还在 `processing`，也允许进入 chunks（若库里还没有 chunks，会自动从 Markdown/原文件生成一次）
- 在弹窗里：
  - 勾选/取消“入库”（included）
  - 编辑 chunk 文本并保存
  - 新增/删除 chunk
  - 已入库文档可点“重建向量”

验收点：
- 保存成功后刷新列表仍可看到变更
- 已入库文档修改 chunk 且同步向量后，查询结果会反映新内容

### 4.4 文档审核（管理员）
前端：
- 用管理员账号登录
- 进入“文档审核”
- 普通用户需先在文档 `markdown_ready` 后点击“确认提交”，管理员才会看到该文档进入审核列表
- 选择某文档点击 `Chunks（选择入库）`，勾选部分 chunk
- 点击“审批通过（按入库选择）”
- 若点击“拒绝”：文档状态变为 `rejected`；用户端可在“我的知识库”看到拒绝原因并点击“重新提交”再次进入审核流程

验收点：
- 文档变为 `indexed`
- 查询只会命中 `included=true` 的 chunks

### 4.5 查询（可选 rerank）
前端：
- 进入“知识库查询”
- 选择 `LLM Provider`：
  - `ollama`：模型从 tags 下拉选择
  - `vllm/xinference`：模型手动输入
- 可选开启 `Rerank`（仅配置了 Xinference rerank 时有效；未配置也不应阻断查询）

验收点：
- 能返回答案 + sources 列表
- 未配置 rerank 时，开启 rerank 也不会导致报错（会自动跳过）

### 4.6 设置（用户级默认参数 + 连通性测试）
前端：
- 进入“设置”
- 修改默认 provider/model/top_k/temperature
- 点击“测试 LLM 连通”（必要时先填写 vLLM/Xinference 的 base_url 和 key 到 `.env`）

验收点：
- 保存后，查询页默认值会刷新
- 连通性测试返回 OK/失败原因

### 4.7 验收审查（生成固定格式报告）
前端：
- 进入“验收审查”
- 上传验收报告（支持同上传页的常用格式）
- 选择审查范围（管理员可选“全库/指定用户/仅本人”）
- 点击“生成审查报告”，并下载 `.md`

验收点：
- 结果以 `# 验收审查报告` 开头
- sources 列表展示依据条款来源

---

## 5. 冒烟测试（推荐）

推荐直接在容器内跑（依赖齐全，且避免宿主机 Python 环境差异）：

- `docker compose exec backend python /scripts/sdk_smoke_test.py --api-url http://localhost:8000/api/v1 --auto-register --model <YOUR_MODEL>`

覆盖内容（脚本会打印每步结果）：
- health、注册/登录、上传、Markdown 上传/下载、确认、管理员审批索引、查询
- chunk CRUD + 向量同步 + 重建向量
- rerank 兼容（未配置也不阻断）
- 验收审查生成

---

## 6. 修改功能后的维护与重打包

目标：**只改哪里，就只重建/导出哪里**，避免重复下载、节省流量。

### 6.1 修改后端（FastAPI / Celery）
1) 改代码（`backend/`）
2) 外网机器重建镜像（避免 pull）：
- `docker compose build --pull=false backend`
3) 外网机器只导出后端镜像：
- `docker save -o offline/images/ragsystem_backend_local.tar ragsystem_backend:local`
4) 内网机器导入并重启：
- `docker load -i offline/images/ragsystem_backend_local.tar`
- `docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d`

> `celery_worker` 也复用后端镜像，所以更新后端镜像即可同时更新 worker。

### 6.2 修改前端（静态页面）
1) 改代码（`frontend/`）
2) 构建：
- `docker compose build --pull=false frontend`
3) 只导出前端镜像：
- `docker save -o offline/images/ragsystem_frontend_local.tar ragsystem_frontend:local`
4) 内网导入并重启：
- `docker load -i offline/images/ragsystem_frontend_local.tar`
- `docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d`

### 6.3 新增 Python 依赖（内网不能 pip）
推荐：外网修改 `backend/requirements.txt` → 外网 `docker compose build --pull=false backend` → 导出镜像 → 内网导入。

应急方案（不推荐长期使用）：参考 `OFFLINE_DEPLOYMENT.md` 的 “whl 应急固化” 流程（`docker cp` + `pip install` + `docker commit`）。

### 6.4 如何验证“改动只影响目标功能”
- 改动后至少跑一次：
  - `docker compose exec backend python /scripts/sdk_smoke_test.py --api-url http://localhost:8000/api/v1 --auto-register --model <YOUR_MODEL>`
- 若改的是前端交互，至少验证对应页面的按钮/流程是否完整闭环（见第 4 节）。

---

## 7. 常见问题排查

### 7.1 前端能打开但请求失败
- 先看“设置”页的 `API Base` 是否正确（必要时用 “API Base 覆盖”）
- 后端是否在 `8001` 监听：`Invoke-WebRequest -UseBasicParsing http://localhost:8001/api/v1/health`

### 7.2 文档一直显示 `processing`
- 看 worker 日志：`docker compose logs --tail 200 celery_worker`
- 常见原因：worker 未运行/崩溃；或启用 `MINERU_USE_MAGIC_PDF=true` 后缺依赖/模型下载慢（默认已开启；失败会自动走降级解析 + OCR）

### 7.3 查询没有命中 sources
- 检查文档是否 `indexed`
- 检查 embedding 模型与维度：
  - `EMBEDDING_DIMENSION` 必须与 embedding 输出一致
  - 不建议在已有数据后随意改维度/collection
- 若日志出现 `input length exceeds the context length`：已对 Ollama embeddings 做自动截断重试；仍异常可适当调小 `CHUNK_SIZE`
- 若 Milvus volumes 重置导致向量为空：可用管理员接口重建向量 `POST /api/v1/admin/reindex`

### 7.5 管理员一键重建索引（Milvus 为空/迁移后）
- 重建指定文档：`POST /api/v1/admin/reindex` body=`{"document_ids":[20]}`
- 重建某个用户的已入库文档：`POST /api/v1/admin/reindex` body=`{"owner_id": 1, "status_in": ["indexed"]}`

### 7.4 vLLM / Xinference 查询失败
- 在“设置”页点击“测试 LLM 连通”
- 确认 `.env` 里 `VLLM_BASE_URL` / `XINFERENCE_BASE_URL` 可从容器访问

---

## 8. 数据与备份提示
数据默认落在 Docker volumes（Postgres/Milvus/MinIO/Redis/MinerU cache）。
- 迁移到新机器时，若只拷贝代码与镜像，历史数据不会自动带过去（volumes 仍为空）。
- 如需要迁移历史数据：应单独规划 volumes 的导出/导入（通常是停服务后打包 Docker volume 数据目录）。
