# 变更日志 (CHANGELOG)

本文档记录 RAG 系统的所有重要变更。

格式遵循：[Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)

---

## [未发布]

### 2026-01-10

#### 新增 (Added)
- 🎉 **Milvus 向量浏览系统**：全新3D可视化界面
  - **3D散点图**：使用Plotly.js实现可拖动、旋转、缩放的3D向量空间可视化
  - **PCA/t-SNE降维**：支持快速PCA或高质量t-SNE降维，展示向量分布
  - **交互式探索**：点击图表中的点查看对应chunk详情
  - **按文档着色**：不同文档的chunk用不同颜色标识，便于区分
  - **Chunk浏览器**：左侧列表展示所有chunk内容，支持实时搜索和按文档筛选
  - **深色主题UI**：深蓝渐变背景、毛玻璃效果、高对比度设计
  - **详情面板**：显示chunk完整内容、元数据（文档名、分段索引、字符数）
  - **分页显示**：支持20/50/100条每页，便于浏览大量chunk
  - **API端点**：
    - `GET /api/v1/milvus/visualization/stats` - 获取向量统计信息
    - `GET /api/v1/milvus/visualization/embeddings` - 获取3D降维坐标
    - `GET /api/v1/milvus/partitions` - 列出所有分区
    - `GET /api/v1/milvus/stats` - 获取集合统计和索引信息

- ✨ **文档库管理系统**：用户可以创建多个文档库来分类管理文档
  - 支持创建/编辑/删除文档库
  - 支持为每个文档库配置embedding和切分策略
  - 上传时可以选择文档库
  - 查询时可以选择检索特定文档库
  - 验收审查时可以选择依据文档库
  - 文档审核时可以按文档库过滤
- ✨ **文档切分预览功能**：上传前预览文档切分效果
  - 支持4种RAGFlow切分策略（character、recursive、token、semantic）
  - 实时调整chunk_size、overlap_percent、delimiters等参数
  - 可视化展示切分统计（总chunk数、平均大小、最小/最大等）
  - 集成Chart.js展示chunk大小分布图
  - 在文档列表和审核页面都可以预览切分
- ✨ **OCR模式选择**：上传扫描件时可以选择OCR模式
  - **自动模式**（auto）：文本过少时自动触发OCR
  - **强制OCR**（force）：始终使用OCR识别（适合扫描件/图片PDF）
  - **禁用OCR**（disable）：仅提取文本（适合纯文本PDF）
- ✨ **图像自动矫正选项**：支持自动检测和矫正PDF页面旋转
  - 上传时可选择是否启用图像偏转矫正
  - 实验性功能，适用于扫描有偏转的文档
- ✨ **Chart.js本地化**：Chart.js下载到本地，完全支持离线部署
- 🎨 **前端UI改进**：
  - 添加文档库管理页面
  - 添加切分预览模态框（含图表和统计）
  - 上传页面增加文档库、OCR和矫正选项
  - 查询和审核页面增加文档库过滤

#### 改进 (Changed)
- 🔧 **Settings API修复**：添加缺失的embedding和chunking配置字段
- 🔧 **UserSettings模型更新**：添加chunk_overlap_percent和chunk_delimiters字段
- 🔧 **Utils工具函数**：添加showModal/hideModal模态框操作函数
- 🔧 **验收审查和文档审核**：新增文档库选择/过滤功能
- 🔧 **前端模块初始化**：LibrariesPage和ChunkPreview模块自动初始化

#### 数据库变更
- 新增 `document_libraries` 表（文档库管理）
- 新增 `documents.ocr_mode` 字段（OCR模式）
- 新增 `documents.deskew` 字段（图像矫正）
- 新增 `user_settings.chunk_overlap_percent` 字段
- 新增 `user_settings.chunk_delimiters` 字段
- 更新 `documents.library_id` 外键（文档库关联）

#### 文档更新
- 📝 更新 `CHANGELOG.md`：添加文档库和切分预览功能说明
- 📝 待更新 `CLAUDE.md`：添加新功能详细说明
- 📝 待更新 `README_RAGFLOW.md`：补充文档库使用说明

#### 技术细节
**新增API端点**：
- `GET/POST/PUT/DELETE /api/v1/libraries` - 文档库CRUD
- `POST /api/v1/chunks/preview` - 切分预览
- `GET /api/v1/review/pending?library_id=X` - 按库过滤审核文档
- `POST /api/v1/acceptance/run` 支持library_id参数
- `POST /api/v1/documents/upload` 支持ocr_mode和deskew参数

**新增前端模块**：
- `frontend/js/libraries.js` - 文档库管理
- `frontend/js/chunkPreview.js` - 切分预览
- `frontend/js/chart.umd.min.js` - Chart.js（本地化）

---

### 2024-01-09

#### 新增 (Added)
- ✨ **多 LLM 后端支持**：部署脚本现在支持 Ollama、Xinference、vLLM、LocalAI 等多种后端
- ✨ **部署脚本改进**：
  - 自动创建 `.env` 文件（如果不存在）
  - 友好的 LLM 后端启动提示
  - 不再强制检查 Ollama 服务
- ✨ **文档新增**：
  - **README_RAGFLOW.md - "重新构建和维护"章节**：详细的重新构建、重启、日志查看、清理操作指南
  - **CHANGELOG.md**：完整的变更日志，记录所有重要改动

#### 改进 (Changed)
- 🐛 **Windows 中文乱码修复**：`deploy.bat` 添加 `chcp 65001`，解决 Windows 控制台中文显示问题
- 🔧 **离线构建改进**：`backend/Dockerfile` 支持通过 `REGISTRY_MIRROR=` 实现离线构建
  - 使用 Bash 参数扩展：`${REGISTRY_MIRROR:+${REGISTRY_MIRROR}/}`
  - 当 `REGISTRY_MIRROR` 为空时，Docker 使用本地已有镜像
  - 添加详细的离线构建注释说明
- 🔧 **Docker Compose 配置优化**：
  - 删除 Docker 版 Ollama 服务定义（默认使用本地 Ollama）
  - 保留注释说明如何恢复 Docker 版 Ollama
  - 删除 `ollama_data` volume（不再需要）
- 📝 **文档更新**：
  - `README_RAGFLOW.md`：
    - 添加支持的 LLM 后端表格和说明
    - 新增"重新构建和维护"章节（详细的操作指南）
    - 添加常见场景（修改代码、环境变量、依赖等）
  - `OFFLINE_DEPLOYMENT.md`：
    - 添加离线构建改进的详细说明
    - 更新增量更新章节，添加在线环境快速参考
  - `.env.example`：添加离线部署配置说明

#### 修复 (Fixed)
- 🐛 修复部署脚本强制检查 Ollama 导致其他后端用户无法部署的问题
- 🐛 修复离线环境 Dockerfile 尝试从远程拉取镜像的问题

#### 技术细节 (Technical Details)

**backend/Dockerfile 改进**：

```dockerfile
# 旧版本（离线会失败）：
FROM ${REGISTRY_MIRROR}/library/python:3.10-slim-bookworm

# 新版本（支持离线）：
ARG REGISTRY_MIRROR=docker.m.daocloud.io
FROM ${REGISTRY_MIRROR:+${REGISTRY_MIRROR}/}library/python:${PYTHON_VERSION}
```

**工作原理**：
- 当 `REGISTRY_MIRROR=docker.m.daocloud.io`：`FROM docker.m.daocloud.io/library/python:3.10-slim-bookworm`
- 当 `REGISTRY_MIRROR=`（为空）：`FROM library/python:3.10-slim-bookworm`（使用本地镜像）

**deploy.bat 编码修复**：

```batch
@echo off
REM 设置 UTF-8 编码以支持中文显示
chcp 65001 >nul 2>&1
```

---

## [0.2.0] - 2024-12-XX

#### RAGFlow-Inspired 特性完整实现

**新增功能**：
- ✅ 多租户 embedding 配置（Ollama、Xinference、LocalAI）
- ✅ 4 种文档切分策略（character、recursive、token、semantic）
- ✅ Token-aware chunking（tiktoken cl100k_base）
- ✅ 重叠百分比配置（0-90%）
- ✅ 自定义分隔符支持（`\n\n`、`###` 等）
- ✅ Embedding 模型自动发现和测试
- ✅ 智能错误提示和配置验证
- ✅ 前端设置 UI（embedding + chunking 配置）

**技术实现**：
- `backend/app/services/embedding_service.py`：多 provider 支持、模型发现、测试
- `backend/app/services/text_splitter.py`：4 种切分策略实现
- `backend/app/api/diagnostics.py`：embedding 测试和诊断 API
- `frontend/js/settings.js`：设置页面逻辑
- `frontend/app.html`：配置 UI

**文档**：
- `README_RAGFLOW.md`：完整的 RAGFlow 特性文档
- `.env.example`：新增 RAGFlow 配置参数

---

## [0.1.0] - 2024-XX-XX

#### 初始版本

**核心功能**：
- ✅ 多租户 RAG 系统（per-user Milvus partitions）
- ✅ 文档上传和审核工作流
- ✅ MinerU PDF→Markdown 转换（异步）
- ✅ 向量搜索和知识库查询
- ✅ 管理员审核和跨用户查询
- ✅ 基于 Docker Compose 的完整部署

**架构组件**：
- PostgreSQL：元数据库
- Redis：缓存 + Celery broker
- Milvus：向量数据库
- MinIO：对象存储
- FastAPI：后端 API
- Celery：异步任务处理
- Nginx：前端静态文件服务

**文档**：
- `README.md`：项目概述
- `CLAUDE.md`：开发者指南
- `OFFLINE_DEPLOYMENT.md`：离线部署指南

---

## 版本命名规则

- **主版本号**：重大架构变更或不兼容更新
- **次版本号**：新功能添加
- **修订号**：Bug 修复和小改进

---

## 变更类型说明

- **新增 (Added)**：新功能
- **改进 (Changed)**：现有功能的变更
- **弃用 (Deprecated)**：即将移除的功能
- **移除 (Removed)**：已移除的功能
- **修复 (Fixed)**：Bug 修复
- **安全 (Security)**：安全相关的修复或改进
