# 多租户 RAG 系统实施计划

## 2026-01 现状补充（与代码保持一致）

- `docx`：上传后直接生成 Markdown + chunks（无需等待 Celery/MinerU）
- `pdf`：默认启用 MinerU/magic-pdf（失败自动降级到常规解析 + OCR，并写入 Markdown）
- 拒绝流：用户端可看到拒绝原因并“重新提交”；管理员默认列表隐藏 `rejected`（可用筛选查看）
- 设置页：展示后端 `.env` 的 Ollama/Xinference Base URL 与 embedding 配置，并可一键测试连通性
- 冒烟测试：`scripts/sdk_smoke_test.py` 会等待 `markdown_ready` 再 confirm/approve（避免“等待转换”误判）

## 当前进度

### ✅ 已完成
1. **数据库模型更新** - `backend/app/models/document.py`
   - 添加 `owner_id` (多租户隔离)
   - 添加 `markdown_path`, `markdown_status`, `markdown_error` (MinerU支持)

2. **数据库迁移文件** - `backend/alembic/versions/023e2c73bbf7_*.py`
   - 安全地添加新字段
   - 为已有文档设置 owner_id
   - 创建必要的索引

### 🔄 待实施 (按优先级)

#### Phase 1: 核心依赖和基础设施 (关键)
1. **更新 requirements.txt**
   ```
   celery==5.3.4
   magic-pdf==0.7.0  # MinerU
   ```

2. **创建 Celery 配置** - `backend/tasks/celery_app.py`
   ```python
   from celery import Celery
   from app.config import settings

   celery_app = Celery(
       "knowledge_base",
       broker=settings.CELERY_BROKER_URL,
       backend=settings.CELERY_RESULT_BACKEND
   )
   ```

3. **创建 MinerU 转换任务** - `backend/tasks/mineru_tasks.py`
   - `convert_to_markdown(document_id)` 异步任务
   - 处理 PDF→Markdown 转换
   - 错误处理和重试机制

#### Phase 2: 服务层更新 (核心逻辑)
4. **更新 MinIO 服务** - `backend/app/services/minio_service.py`
   - 添加 `get_user_path(user_id, type)` 方法
   - 支持 `user_{id}/documents/` 和 `user_{id}/markdown/` 路径

5. **更新 Milvus 服务** - `backend/app/services/milvus_service.py`
   - 添加 `create_partition(partition_name)` 方法
   - 更新 `insert_vectors()` 支持 partition_name 参数
   - 更新 `search()` 支持 partition_names 过滤

6. **更新 RAG 服务** - `backend/app/services/rag_service.py`
   - `query()` 方法添加 partition_names 参数
   - `index_document()` 支持用户分区
   - 使用 Markdown 内容而非原始 PDF

#### Phase 3: API 端点更新 (用户接口)
7. **更新 documents.py** - `backend/app/api/documents.py`
   - 修改 `upload_document()`: 设置 owner_id, 触发 Celery任务
   - 添加 `get_document_status()`: 查询 Markdown 转换状态
   - 添加 `download_markdown()`: 下载转换后的 Markdown
   - 添加 `upload_markdown()`: 用户上传编辑后的 Markdown
   - 修改 `list_documents()`: 添加 owner_id 过滤

8. **更新 query.py** - `backend/app/api/query.py`
   - 修改 `query()`: 仅查询用户自己的分区
   - 添加 `admin_query()`: 管理员跨库查询

9. **更新 review.py** - `backend/app/api/review.py`
   - `approve_document()`: 使用 Markdown 内容索引到用户分区

#### Phase 4: Docker 配置更新
10. **更新 docker-compose.yml**
    - 添加 celery_worker 服务
    - 添加 CELERY_BROKER_URL 环境变量
    - 添加 mineru_models volume

11. **更新 .env.example**
    - 添加 Celery 配置项

#### Phase 5: 测试
12. **创建测试脚本** - `scripts/test_multi_tenant.py`
    - 测试用户注册
    - 测试文档上传和 MinerU 转换
    - 测试 Markdown 下载/上传
    - 测试审核和索引到分区
    - 测试多租户隔离查询

## 实施建议

### 方案 A: 渐进式实施 (推荐)
1. 先运行数据库迁移
2. 实施 Phase 1-2 (核心功能)
3. 测试基本流程
4. 实施 Phase 3 (API)
5. 完整测试

### 方案 B: 完整实施
一次性实施所有功能，适合有充足测试时间的情况。

## 风险点

1. **MinerU 依赖较大** (~GB级模型下载)
   - 首次转换会很慢
   - 建议预下载模型

2. **数据库迁移需要停机**
   - owner_id 需要为已有文档设置值
   - 建议在低峰期执行

3. **Milvus 分区重建**
   - 已有向量数据需要重新索引到用户分区
   - 需要编写迁移脚本

## 下一步行动

选择以下之一:

A. **继续自动实施** - 我会逐步创建所有必要文件
B. **手动实施** - 我提供具体代码，你手动创建
C. **分阶段实施** - 每完成一个 Phase 就测试一次

请告诉我你的选择！
