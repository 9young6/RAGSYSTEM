# 企业级文档管理+RAG知识库系统架构方案

## 📋 需求分析

### 核心流程（多租户知识库）
```
普通用户流程：
用户上传(PDF/DOCX)
  ↓ MinerU 解析为 Markdown
  ↓ 用户下载预览 Markdown
  ↓ 用户编辑后上传 Markdown
  ↓ 管理员内容审核
  ↓ 存储到用户专属 Milvus 知识库
  ↓ 用户在自己的知识库中查询

管理员流程：
  ↓ 可以访问所有用户的知识库
  ↓ 审核所有用户的文档
  ↓ 可以在任意知识库中查询
```

### 关键约束
- ✅ 内网部署
- ✅ 容器化（Docker）
- ✅ 提供API调用
- ✅ 本地LLM配置
- ✅ Python编程友好
- ✅ 前端交互界面
- ✅ 大模型能理解的架构
- ✅ **多租户隔离**：每个用户独立知识库
- ✅ **MinerU集成**：高质量 PDF→Markdown 转换
- ✅ **管理员权限**：跨知识库访问

---

## 🏗️ 系统架构设计

### 分层架构

```
┌─────────────────────────────────────────────────────┐
│                    前端层 (Web UI)                   │
│         Vue3/React + Ant Design/Element UI          │
├─────────────────────────────────────────────────────┤
│                  API网关层 (FastAPI)                 │
│        统一入口、认证、限流、日志、错误处理          │
├──────────────┬──────────────┬──────────────┐────────┤
│   文档处理   │  内容审核    │  知识库查询  │  LLM   │
│   服务       │  服务        │  服务        │  服务  │
├──────────────┼──────────────┼──────────────┼────────┤
│  MinerU     │  规则引擎    │  LangChain  │ Ollama │
│  PDF→MD     │  /LLM审核    │  + Milvus   │ /本地  │
│  转换       │              │  (多租户)    │ LLM   │
├─────────────────────────────────────────────────────┤
│            数据存储层                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ Milvus      │  │ PostgreSQL   │  │ MinIO/     │  │
│  │ 向量库      │  │ 元数据/      │  │ 文件存储   │  │
│  │ (分区隔离)  │  │ 审核记录     │  │ (原始+MD)  │  │
│  └─────────────┘  └──────────────┘  └────────────┘  │
├─────────────────────────────────────────────────────┤
│              基础设施 (Docker Compose)                │
└─────────────────────────────────────────────────────┘
```

---

## 🛠️ 技术栈选型

### 后端核心
| 组件 | 技术方案 | 原因 |
|------|---------|------|
| **Web框架** | FastAPI | 异步高性能、自动API文档、强类型校验 |
| **LLM集成** | LangChain + Ollama | 本地化、易扩展、支持多种LLM |
| **向量数据库** | Milvus | 企业级、支持多租户、API完善 |
| **文档解析** | MinerU | 高质量PDF→Markdown转换，保留布局 |
| **数据库** | PostgreSQL | 稳定、支持JSON、元数据管理 |
| **消息队列** | Celery + Redis | 异步任务、长流程处理（MinerU转换） |
| **文件存储** | MinIO | S3兼容、内网友好 |

### 前端
| 组件 | 技术方案 |
|------|---------|
| **框架** | Vue 3 / React 18 |
| **UI库** | Element Plus / Ant Design |
| **状态管理** | Pinia / Zustand |
| **HTTP客户端** | axios |

### 部署
| 组件 | 技术方案 |
|------|---------|
| **容器化** | Docker + Docker Compose |
| **编排** | Docker Compose（单机）/ Kubernetes（集群） |

---

## 🏢 多租户知识库架构

### 核心设计原则

1. **数据隔离**：每个用户拥有独立的知识库分区
2. **权限控制**：普通用户只能访问自己的知识库，管理员可跨库访问
3. **资源共享**：所有用户共享 Ollama LLM 和嵌入模型服务
4. **可扩展性**：支持大量用户并发使用

### 多租户实现方案

#### 1. PostgreSQL 数据隔离
```sql
-- documents 表增加 owner_id 字段
ALTER TABLE documents ADD COLUMN owner_id INTEGER REFERENCES users(id);

-- 所有查询必须过滤 owner_id
SELECT * FROM documents WHERE owner_id = current_user_id;

-- 管理员可以跨用户查询
SELECT * FROM documents
WHERE owner_id = ? OR current_user.role = 'admin';
```

#### 2. Milvus 分区隔离
```python
# 每个用户一个分区
partition_name = f"user_{user_id}"

# 创建用户分区
collection.create_partition(partition_name)

# 插入时指定分区
collection.insert(data, partition_name=partition_name)

# 查询时过滤分区
collection.search(
    data=query_vectors,
    anns_field="embedding",
    partition_names=[f"user_{user_id}"],  # 普通用户
    # partition_names=None,  # 管理员查询所有分区
    limit=top_k
)
```

#### 3. MinIO 目录隔离
```
knowledge-base/
├── user_1/
│   ├── documents/           # 原始文件
│   │   ├── doc1.pdf
│   │   └── doc2.docx
│   └── markdown/            # 转换后的 Markdown
│       ├── doc1.md
│       └── doc2.md
├── user_2/
│   ├── documents/
│   └── markdown/
└── ...
```

### 权限矩阵

| 操作 | 普通用户 | 管理员 |
|------|---------|--------|
| 上传文档 | ✅ 仅到自己库 | ✅ 仅到自己库 |
| 查看文档列表 | ✅ 仅自己的 | ✅ 所有用户的 |
| 下载 Markdown | ✅ 仅自己的 | ✅ 所有用户的 |
| 上传 Markdown | ✅ 仅到自己库 | ✅ 到任意库 |
| 审核文档 | ❌ | ✅ 审核所有用户 |
| 查询知识库 | ✅ 仅自己的 | ✅ 选择任意库或全部 |
| 删除文档 | ✅ 仅自己的 | ✅ 任意用户的 |

---

## 📄 MinerU 集成方案

### MinerU 简介
MinerU 是高质量的 PDF 文档解析工具，能够：
- 保留原始排版结构
- 提取表格、公式、图片
- 生成高质量 Markdown
- 支持中英文混合文档

### 集成架构

```
用户上传 PDF/DOCX
    ↓
保存到 MinIO (documents/)
    ↓
触发 Celery 异步任务
    ↓
MinerU 转换为 Markdown
    ↓
保存到 MinIO (markdown/)
    ↓
更新 document.markdown_path
    ↓
通知用户可下载预览
```

### API 流程

#### 1. 上传原始文档
```python
POST /api/v1/documents/upload
Content-Type: multipart/form-data

Response:
{
  "document_id": 123,
  "status": "processing",  # MinerU 转换中
  "message": "文档正在转换为 Markdown，请稍后查看"
}
```

#### 2. 轮询转换状态
```python
GET /api/v1/documents/{id}/status

Response:
{
  "document_id": 123,
  "status": "markdown_ready",  # 或 "processing", "failed"
  "markdown_available": true
}
```

#### 3. 下载 Markdown
```python
GET /api/v1/documents/{id}/markdown/download

Response:
Content-Type: text/markdown
Content-Disposition: attachment; filename="document.md"

# 文档标题
这是转换后的内容...
```

#### 4. 用户编辑后上传 Markdown
```python
POST /api/v1/documents/{id}/markdown/upload
Content-Type: multipart/form-data

{
  "file": edited_markdown_file
}

Response:
{
  "document_id": 123,
  "status": "confirmed",  # 等待管理员审核
  "message": "Markdown 已上传，等待审核"
}
```

#### 5. 管理员审核并索引
```python
POST /api/v1/review/approve/{id}

# 系统使用最终的 Markdown 内容进行索引
# 而不是原始 PDF 文本
```

### Celery 任务定义

```python
# tasks/mineru_tasks.py
from celery import shared_task
from magic_pdf.pipe.UNIPipe import UNIPipe
import os

@shared_task(bind=True, max_retries=3)
def convert_to_markdown(self, document_id: int):
    """
    异步转换文档为 Markdown
    """
    try:
        # 1. 从数据库获取文档信息
        document = get_document(document_id)

        # 2. 从 MinIO 下载原始文件
        pdf_bytes = minio_service.download_bytes(document.minio_object)

        # 3. 使用 MinerU 转换
        pdf_path = f"/tmp/{document_id}.pdf"
        with open(pdf_path, 'wb') as f:
            f.write(pdf_bytes)

        pipe = UNIPipe(pdf_path, "/tmp/output")
        pipe.pipe_classify()
        pipe.pipe_parse()
        markdown_content = pipe.pipe_mk_markdown()

        # 4. 上传 Markdown 到 MinIO
        markdown_path = f"user_{document.owner_id}/markdown/{document_id}.md"
        minio_service.upload_bytes(
            markdown_path,
            markdown_content.encode('utf-8')
        )

        # 5. 更新数据库
        document.markdown_path = markdown_path
        document.status = "markdown_ready"
        db.commit()

        # 6. 清理临时文件
        os.remove(pdf_path)

        return {"status": "success", "document_id": document_id}

    except Exception as e:
        # 重试机制
        self.retry(exc=e, countdown=60)
```

---

## 📦 Docker Compose 部署配置

```yaml
version: '3.8'

services:
  # ============ 基础服务 ============
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: secure_password
      POSTGRES_DB: knowledge_base
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U admin"]
      interval: 10s
      timeout: 5s
      retries: 5

  milvus:
    image: milvusdb/milvus:v0.4.12
    environment:
      COMMON_STORAGETYPE: local
      ETCD_ENDPOINTS: etcd:2379
      COMMON_ETCD_ENDPOINTS: etcd:2379
    ports:
      - "19530:19530"
      - "9091:9091"
    volumes:
      - milvus_data:/var/lib/milvus
    depends_on:
      etcd:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5

  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
    ports:
      - "2379:2379"
    volumes:
      - etcd_data:/etcd
    healthcheck:
      test: ["CMD", "etcdctl", "endpoint", "health"]
      interval: 10s
      timeout: 5s
      retries: 5

  minio:
    image: minio/minio:latest
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/minio_data
    command: server /minio_data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ============ LLM服务 ============
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0:11434
    # GPU加速（可选）
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]

  # ============ 后端应用 ============
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://admin:secure_password@postgres:5432/knowledge_base
      - MILVUS_HOST=milvus
      - MILVUS_PORT=19530
      - REDIS_URL=redis://redis:6379
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
      - OLLAMA_BASE_URL=http://ollama:11434
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=minioadmin
      - MINIO_SECRET_KEY=minioadmin
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      milvus:
        condition: service_healthy
      ollama:
        condition: service_started
    volumes:
      - ./backend:/app
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  # ============ Celery Worker (MinerU 处理) ============
  celery_worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      - DATABASE_URL=postgresql://admin:secure_password@postgres:5432/knowledge_base
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=minioadmin
      - MINIO_SECRET_KEY=minioadmin
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
    depends_on:
      - redis
      - postgres
      - minio
    volumes:
      - ./backend:/app
      - mineru_models:/root/.cache/huggingface  # MinerU 模型缓存
    command: celery -A tasks.celery_app worker --loglevel=info --concurrency=2
    # GPU 支持（可选，用于 MinerU 加速）
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]

  # ============ 前端应用 ============
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://backend:8000
    depends_on:
      - backend
    volumes:
      - ./frontend:/app

volumes:
  postgres_data:
  redis_data:
  milvus_data:
  etcd_data:
  minio_data:
  ollama_data:
  mineru_models:  # MinerU 模型缓存

networks:
  default:
    name: knowledge_base_network
```

---

## 💻 后端核心实现

### 项目结构

```
backend/
├── main.py                 # FastAPI应用入口
├── config.py              # 配置管理
├── requirements.txt       # 依赖
├── Dockerfile             # 容器配置
├── alembic/              # 数据库迁移
├── app/
│   ├── __init__.py
│   ├── schemas/          # Pydantic模型
│   │   ├── document.py
│   │   ├── review.py
│   │   └── query.py
│   ├── models/           # SQLAlchemy模型
│   │   ├── document.py
│   │   ├── review.py
│   │   └── user.py
│   ├── api/              # API路由
│   │   ├── documents.py
│   │   ├── review.py
│   │   ├── query.py
│   │   └── health.py
│   ├── services/         # 业务逻辑
│   │   ├── document_service.py
│   │   ├── review_service.py
│   │   ├── rag_service.py
│   │   └── llm_service.py
│   ├── utils/
│   │   ├── document_parser.py
│   │   ├── text_splitter.py
│   │   └── embedding.py
│   └── middleware/
│       ├── auth.py
│       └── error_handler.py
```

### main.py 核心代码

```python
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List
import logging

from config import settings
from app.models import Base
from app.database import engine, get_db
from app.api import documents, review, query, health
from app.middleware.error_handler import setup_error_handlers

# 初始化日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建表
Base.metadata.create_all(bind=engine)

# 创建FastAPI应用
app = FastAPI(
    title="知识库管理系统API",
    description="支持文档上传、审核、查询的RAG系统",
    version="1.0.0"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 内网环境，可配置具体来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 错误处理中间件
setup_error_handlers(app)

# 路由注册
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(documents.router, prefix="/api/v1", tags=["Documents"])
app.include_router(review.router, prefix="/api/v1", tags=["Review"])
app.include_router(query.router, prefix="/api/v1", tags=["Query"])

# 启动事件
@app.on_event("startup")
async def startup_event():
    logger.info("应用启动，初始化连接...")
    # 初始化Milvus、Redis等连接
    await init_services()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("应用关闭...")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 文档上传API

```python
# app/api/documents.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.schemas.document import DocumentCreate, DocumentResponse
from app.services.document_service import DocumentService
from app.database import get_db
from sqlalchemy.orm import Session

router = APIRouter()

@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    上传文档（DOCX/PDF）
    
    返回解析后的预览内容，等待用户确认
    """
    # 文件验证
    if not file.filename.endswith(('.pdf', '.docx')):
        raise HTTPException(status_code=400, detail="仅支持PDF和DOCX格式")
    
    service = DocumentService(db)
    result = await service.parse_and_preview(file, user_id)
    
    return {
        "status": "pending_confirmation",
        "document_id": result["id"],
        "preview": result["preview"],
        "metadata": result["metadata"]
    }

@router.post("/documents/confirm/{document_id}")
async def confirm_document(
    document_id: int,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """用户确认文档内容"""
    service = DocumentService(db)
    result = await service.confirm_document(document_id, user_id)
    
    return {
        "status": "pending_review",
        "document_id": document_id,
        "message": "已提交管理员审核"
    }
```

### 内容审核API

```python
# app/api/review.py
from fastapi import APIRouter, HTTPException, Depends
from app.schemas.review import ReviewAction
from app.services.review_service import ReviewService
from app.database import get_db
from sqlalchemy.orm import Session

router = APIRouter()

@router.get("/review/pending")
async def get_pending_reviews(
    admin_id: int = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """获取待审核文档列表"""
    service = ReviewService(db)
    documents = await service.get_pending_documents()
    
    return {
        "total": len(documents),
        "documents": documents
    }

@router.post("/review/approve/{document_id}")
async def approve_document(
    document_id: int,
    admin_id: int = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """批准文档并入库"""
    service = ReviewService(db)
    await service.approve_and_index(document_id)
    
    return {"status": "approved", "document_id": document_id}

@router.post("/review/reject/{document_id}")
async def reject_document(
    document_id: int,
    reason: str,
    admin_id: int = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """拒绝文档"""
    service = ReviewService(db)
    await service.reject(document_id, reason)
    
    return {"status": "rejected", "document_id": document_id}
```

### RAG查询API

```python
# app/api/query.py
from fastapi import APIRouter, HTTPException, Depends
from app.schemas.query import QueryRequest, QueryResponse
from app.services.rag_service import RAGService
from app.database import get_db
from sqlalchemy.orm import Session

router = APIRouter()

@router.post("/query")
async def query_knowledge_base(
    request: QueryRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> QueryResponse:
    """
    查询知识库并使用本地LLM生成回答
    
    流程：
    1. 向量化查询
    2. Milvus检索相关文档
    3. LLM生成回答
    """
    service = RAGService(db)
    
    try:
        response = await service.query(
            query_text=request.query,
            top_k=request.top_k or 5,
            llm_model=request.model or "llama2",
            temperature=request.temperature or 0.7
        )
        
        return QueryResponse(
            query=request.query,
            answer=response["answer"],
            sources=response["sources"],
            confidence=response["confidence"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 核心服务类

```python
# app/services/rag_service.py
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import Milvus
from langchain.chains import RetrievalQA
from langchain.llms import Ollama
from pymilvus import Collection, connections
import logging

logger = logging.getLogger(__name__)

class RAGService:
    def __init__(self, db):
        self.db = db
        self.milvus_host = settings.MILVUS_HOST
        self.milvus_port = settings.MILVUS_PORT
        
        # 初始化向量模型
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/paraphrase-MiniLM-L6-v2"
        )
        
        # 初始化本地LLM
        self.ollama_client = Ollama(
            base_url=settings.OLLAMA_BASE_URL,
            model="llama2"
        )
    
    async def query(self, query_text: str, top_k: int = 5, 
                   llm_model: str = "llama2", temperature: float = 0.7):
        """执行RAG查询"""
        
        # 1. 连接Milvus
        connections.connect(
            alias="default",
            host=self.milvus_host,
            port=self.milvus_port
        )
        
        # 2. 创建向量存储实例
        vector_store = Milvus(
            embedding_function=self.embeddings,
            collection_name="knowledge_base",
            connection_args={
                "host": self.milvus_host,
                "port": self.milvus_port
            }
        )
        
        # 3. 检索相关文档
        retriever = vector_store.as_retriever(search_kwargs={"k": top_k})
        
        # 4. 构建RAG链
        qa_chain = RetrievalQA.from_chain_type(
            llm=self.ollama_client,
            chain_type="stuff",
            retriever=retriever,
            return_source_documents=True
        )
        
        # 5. 执行查询
        result = qa_chain({"query": query_text})
        
        # 6. 提取结果
        sources = [doc.metadata for doc in result["source_documents"]]
        
        return {
            "answer": result["result"],
            "sources": sources,
            "confidence": 0.85  # 可根据业务计算
        }
    
    async def index_document(self, document_id: int, chunks: List[str]):
        """将文档chunks索引到Milvus"""
        
        # 生成向量
        embeddings = self.embeddings.embed_documents(chunks)
        
        # 存储到Milvus
        vector_store = Milvus.from_documents(
            documents=[...],
            embedding=self.embeddings,
            collection_name="knowledge_base",
            connection_args={
                "host": self.milvus_host,
                "port": self.milvus_port
            }
        )
        
        logger.info(f"Document {document_id} indexed successfully")
```

### 文档解析服务

```python
# app/services/document_service.py
from app.utils.document_parser import parse_pdf, parse_docx
from app.utils.text_splitter import split_text
from sqlalchemy.orm import Session
import tempfile
import os

class DocumentService:
    def __init__(self, db: Session):
        self.db = db
    
    async def parse_and_preview(self, file, user_id: int):
        """解析文档并生成预览"""
        
        # 保存临时文件
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # 根据文件类型解析
            if file.filename.endswith('.pdf'):
                text = parse_pdf(tmp_path)
            elif file.filename.endswith('.docx'):
                text = parse_docx(tmp_path)
            
            # 文本分割（用于预览）
            chunks = split_text(text, chunk_size=500)
            
            # 保存文档记录
            doc = Document(
                filename=file.filename,
                original_text=text,
                user_id=user_id,
                status="pending_confirmation"
            )
            self.db.add(doc)
            self.db.commit()
            
            return {
                "id": doc.id,
                "preview": chunks[:3],  # 预览前3个chunks
                "metadata": {
                    "filename": file.filename,
                    "size": len(content),
                    "chunks_count": len(chunks)
                }
            }
        finally:
            os.unlink(tmp_path)
```

---

## 🎨 前端架构

### Vue 3 + TypeScript 项目结构

```
frontend/
├── src/
│   ├── App.vue
│   ├── main.ts
│   ├── api/
│   │   ├── client.ts        # Axios配置
│   │   ├── documents.ts
│   │   ├── review.ts
│   │   └── query.ts
│   ├── stores/
│   │   ├── auth.ts          # 用户认证
│   │   ├── documents.ts
│   │   └── app.ts
│   ├── views/
│   │   ├── DocumentUpload.vue
│   │   ├── ReviewPanel.vue
│   │   └── QueryInterface.vue
│   ├── components/
│   │   ├── FileUploader.vue
│   │   ├── DocumentPreview.vue
│   │   └── QueryResult.vue
│   └── utils/
│       └── formatting.ts
├── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```

### 核心页面示例

```vue
<!-- DocumentUpload.vue -->
<template>
  <div class="upload-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>上传文档</span>
        </div>
      </template>

      <!-- 上传区域 -->
      <el-upload
        v-model:file-list="fileList"
        action="/api/v1/documents/upload"
        :auto-upload="false"
        accept=".pdf,.docx"
        drag
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此或<em>点击选择</em>
        </div>
      </el-upload>

      <!-- 上传按钮 -->
      <el-button type="primary" @click="handleUpload">
        上传文档
      </el-button>

      <!-- 预览结果 -->
      <el-alert v-if="preview" type="info" :closable="false">
        <template #title>
          <h4>文档预览</h4>
        </template>
        <div class="preview-content">
          <p v-for="(chunk, i) in preview.chunks" :key="i">
            {{ chunk }}
          </p>
        </div>
        <el-button type="success" @click="confirmDocument">
          确认提交审核
        </el-button>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { uploadDocument, confirmDocument } from '@/api/documents'

const fileList = ref([])
const preview = ref(null)

const handleUpload = async () => {
  if (fileList.value.length === 0) {
    ElMessage.error('请选择文件')
    return
  }

  const file = fileList.value[0].raw
  const formData = new FormData()
  formData.append('file', file)

  try {
    const response = await uploadDocument(formData)
    preview.value = response.data
  } catch (error) {
    ElMessage.error('上传失败')
  }
}

const confirmDocument = async () => {
  try {
    await confirmDocument(preview.value.document_id)
    ElMessage.success('已提交审核')
    fileList.value = []
    preview.value = null
  } catch (error) {
    ElMessage.error('提交失败')
  }
}
</script>
```

---

## 🔧 配置文件

### config.py

```python
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str = "postgresql://admin:password@postgres:5432/knowledge_base"
    
    # Milvus向量数据库
    MILVUS_HOST: str = "milvus"
    MILVUS_PORT: int = 19530
    
    # Redis
    REDIS_URL: str = "redis://redis:6379"
    
    # Ollama LLM
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama2"
    
    # MinIO文件存储
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "knowledge-base"
    
    # 应用配置
    APP_NAME: str = "Knowledge Base Management System"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # 文档处理
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    
    # 向量模型
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-MiniLM-L6-v2"
    
    class Config:
        env_file = ".env"

settings = Settings()
```

### .env 文件

```env
# 数据库
DATABASE_URL=postgresql://admin:secure_password@postgres:5432/knowledge_base

# Milvus
MILVUS_HOST=milvus
MILVUS_PORT=19530

# Redis
REDIS_URL=redis://redis:6379

# Ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama2

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# 应用
DEBUG=False
LOG_LEVEL=INFO
```

---

## 📝 API文档速览

### 核心端点

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/api/v1/documents/upload` | 上传文档 |
| POST | `/api/v1/documents/confirm/{id}` | 确认文档 |
| GET | `/api/v1/review/pending` | 获取待审核文档 |
| POST | `/api/v1/review/approve/{id}` | 审核通过 |
| POST | `/api/v1/review/reject/{id}` | 审核拒绝 |
| POST | `/api/v1/query` | 查询知识库 |
| GET | `/api/v1/health` | 健康检查 |

### 请求/响应示例

```json
// 查询请求
POST /api/v1/query
{
  "query": "Python异步编程是什么？",
  "top_k": 5,
  "model": "llama2",
  "temperature": 0.7
}

// 查询响应
{
  "query": "Python异步编程是什么？",
  "answer": "Python异步编程是一种编程模式，用于处理...",
  "sources": [
    {
      "document_id": 1,
      "document_name": "Python高级编程.pdf",
      "chunk_index": 3,
      "relevance": 0.92
    }
  ],
  "confidence": 0.85
}
```

---

## 🚀 快速启动指南

### 1. 克隆项目
```bash
git clone <repo>
cd knowledge-base-system
```

### 2. 配置环境
```bash
cp .env.example .env
# 编辑.env文件，根据需要调整配置
```

### 3. 启动容器
```bash
docker-compose up -d

# 首次启动需要初始化数据库
docker-compose exec backend alembic upgrade head
```

### 4. 初始化Ollama模型
```bash
# 进入ollama容器
docker-compose exec ollama ollama pull llama2

# 或使用其他模型
docker-compose exec ollama ollama pull mistral
```

### 5. 访问应用
- 前端: http://localhost:3000
- API文档: http://localhost:8000/docs
- Minio控制台: http://localhost:9001

---

## 🔐 安全考虑

1. **认证与授权**
   - JWT Token认证
   - Role-based访问控制（Admin/User）
   - 文档所有权隔离

2. **数据安全**
   - 文件存储加密（MinIO）
   - 数据库连接SSL
   - 敏感信息不写入日志

3. **API安全**
   - 请求签名验证
   - 限流与频率限制
   - CORS配置

---

## 📊 扩展方向

1. **支持更多LLM**
   ```python
   # 轻松集成其他模型
   LLMs = {
       "ollama": Ollama,
       "openai": ChatOpenAI,
       "local_llama": LlamaCpp,
       "huggingface": HuggingFaceHub
   }
   ```

2. **多用户租户隔离**
   - 数据库级隔离
   - Milvus分区隔离

3. **性能优化**
   - 文档分布式处理
   - 向量检索缓存
   - 异步处理管道

4. **监控与日志**
   - ELK Stack集成
   - Prometheus metrics
   - Jaeger链路追踪

---

## 🤝 与大模型的迭代方式

### 架构沟通要点

1. **模块化设计**
   - 清晰的组件边界
   - 标准化输入/输出
   - 易于替换和升级

2. **可观测性**
   - 详细日志记录
   - 性能指标收集
   - 错误追踪

3. **配置驱动**
   - LLM模型可切换
   - Prompt模板可配置
   - 参数（temperature等）可调

4. **版本管理**
   - 模型版本追踪
   - A/B测试支持
   - 快速回滚机制

这样大模型就能理解你的系统架构，根据需求提出优化建议或代码改进方案。

---

## 📚 核心依赖库

```
# requirements.txt
fastapi==0.109.0
uvicorn==0.27.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
pymilvus==2.4.0
langchain==0.1.0
langchain-community==0.0.8
ollama==0.1.0
sentence-transformers==2.2.2
pydantic==2.5.0
redis==5.0.1
celery==5.3.4
magic-pdf==0.7.0  # MinerU 核心库
pdfplumber==0.10.3
python-docx==0.8.11
minio==7.1.16
```

---

## 🗄️ 数据库表结构变更

### 新增字段

#### documents 表
```sql
ALTER TABLE documents
ADD COLUMN owner_id INTEGER REFERENCES users(id) NOT NULL,  -- 文档所有者
ADD COLUMN markdown_path VARCHAR(512),  -- Markdown 文件在 MinIO 的路径
ADD COLUMN markdown_status VARCHAR(32) DEFAULT 'pending',  -- processing | markdown_ready | failed
ADD COLUMN markdown_error TEXT;  -- 转换失败的错误信息

-- 索引优化
CREATE INDEX idx_documents_owner_id ON documents(owner_id);
CREATE INDEX idx_documents_markdown_status ON documents(markdown_status);
CREATE INDEX idx_documents_status_owner ON documents(status, owner_id);
```

#### 文档状态扩展
```
新状态流转：
uploaded → processing → markdown_ready → confirmed → approved → indexed
                     ↓
                   failed (markdown转换失败)
```

### 多租户查询示例

```sql
-- 普通用户：只查看自己的文档
SELECT * FROM documents
WHERE owner_id = :current_user_id
AND status IN ('markdown_ready', 'confirmed', 'indexed');

-- 管理员：查看所有待审核文档
SELECT d.*, u.username as owner_name
FROM documents d
JOIN users u ON d.owner_id = u.id
WHERE d.status = 'confirmed'
ORDER BY d.confirmed_at DESC;

-- 管理员：查看指定用户的知识库
SELECT * FROM documents
WHERE owner_id = :target_user_id
AND status = 'indexed';
```

---

## 📡 API 端点设计（多租户版本）

### 文档管理端点

| 方法 | 端点 | 说明 | 权限 |
|------|------|------|------|
| POST | `/api/v1/documents/upload` | 上传文档，触发 MinerU 转换 | User |
| GET | `/api/v1/documents` | 列出自己的文档（管理员可加 `?user_id=X`） | User/Admin |
| GET | `/api/v1/documents/{id}` | 获取文档详情 | Owner/Admin |
| GET | `/api/v1/documents/{id}/status` | 查询 Markdown 转换状态 | Owner/Admin |
| GET | `/api/v1/documents/{id}/markdown/download` | 下载 Markdown | Owner/Admin |
| POST | `/api/v1/documents/{id}/markdown/upload` | 上传编辑后的 Markdown | Owner/Admin |
| DELETE | `/api/v1/documents/{id}` | 删除文档 | Owner/Admin |

### 审核端点

| 方法 | 端点 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/v1/review/pending` | 获取待审核文档（所有用户） | Admin |
| POST | `/api/v1/review/approve/{id}` | 审核通过并索引到用户分区 | Admin |
| POST | `/api/v1/review/reject/{id}` | 审核拒绝 | Admin |

### 查询端点

| 方法 | 端点 | 说明 | 权限 |
|------|------|------|------|
| POST | `/api/v1/query` | 查询自己的知识库 | User |
| POST | `/api/v1/query/admin` | 查询指定用户或全部知识库 | Admin |

### 用户管理端点

| 方法 | 端点 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/v1/users` | 列出所有用户 | Admin |
| GET | `/api/v1/users/{id}/stats` | 用户知识库统计 | Admin |

---

## 🚀 实施步骤和迁移指南

### 阶段 1：数据库迁移

```bash
# 1. 备份现有数据库
docker compose exec postgres pg_dump -U admin knowledge_base > backup.sql

# 2. 执行迁移
docker compose exec backend alembic revision --autogenerate -m "add_multi_tenant_support"
docker compose exec backend alembic upgrade head

# 3. 数据迁移：为现有文档设置 owner_id
docker compose exec postgres psql -U admin -d knowledge_base -c "
UPDATE documents SET owner_id = uploader_id WHERE owner_id IS NULL;
"
```

### 阶段 2：Milvus 分区重建

```python
# scripts/migrate_milvus_to_partitions.py
from app.services.milvus_service import MilvusService
from app.database import SessionLocal
from app.models import Document

db = SessionLocal()
milvus = MilvusService()

# 1. 获取所有已索引文档
documents = db.query(Document).filter(Document.status == 'indexed').all()

# 2. 按用户分组
user_docs = {}
for doc in documents:
    if doc.owner_id not in user_docs:
        user_docs[doc.owner_id] = []
    user_docs[doc.owner_id].append(doc)

# 3. 为每个用户创建分区并重新索引
for user_id, docs in user_docs.items():
    partition_name = f"user_{user_id}"
    milvus.create_partition(partition_name)

    for doc in docs:
        # 重新索引到用户分区
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).all()
        embeddings = embedding_service.embed_documents([c.content for c in chunks])

        milvus.insert_vectors(
            partition_name=partition_name,
            vectors=embeddings,
            metadata=[{"document_id": doc.id, "chunk_index": i} for i in range(len(chunks))]
        )

print("Migration completed!")
```

### 阶段 3：添加 MinerU 支持

```bash
# 1. 更新 requirements.txt
echo "magic-pdf==0.7.0" >> backend/requirements.txt
echo "celery==5.3.4" >> backend/requirements.txt

# 2. 添加 Celery 配置文件
# backend/tasks/celery_app.py
# backend/tasks/mineru_tasks.py

# 3. 重新构建容器
docker compose build backend celery_worker

# 4. 启动新服务
docker compose up -d celery_worker
```

### 阶段 4：更新 API 代码

```python
# app/api/documents.py 关键修改

@router.post("/documents/upload")
async def upload_document(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. 保存到 MinIO (user_id 隔离)
    object_path = f"user_{current_user.id}/documents/{uuid4()}/{file.filename}"
    minio_service.upload_file(object_path, file)

    # 2. 创建文档记录
    document = Document(
        filename=file.filename,
        owner_id=current_user.id,  # 关键：设置所有者
        status="processing",
        markdown_status="pending",
        minio_object=object_path
    )
    db.add(document)
    db.commit()

    # 3. 触发 Celery 任务
    from tasks.mineru_tasks import convert_to_markdown
    convert_to_markdown.delay(document.id)

    return {
        "document_id": document.id,
        "status": "processing",
        "message": "文档正在转换为 Markdown"
    }


@router.post("/query/admin")
async def admin_query(
    request: QueryRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """管理员跨知识库查询"""
    rag_service = RAGService(db)

    # 指定用户 ID 或 None 表示查询所有
    partition_names = None
    if request.user_id:
        partition_names = [f"user_{request.user_id}"]

    return await rag_service.query(
        query_text=request.query,
        partition_names=partition_names,  # 多租户过滤
        top_k=request.top_k or 5
    )
```

### 阶段 5：前端更新

```javascript
// 新增：下载 Markdown 按钮
async function downloadMarkdown(documentId) {
  const response = await fetch(
    `${API_BASE}/documents/${documentId}/markdown/download`,
    {
      headers: { Authorization: `Bearer ${token}` }
    }
  );

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `document_${documentId}.md`;
  a.click();
}

// 新增：上传编辑后的 Markdown
async function uploadMarkdown(documentId, file) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(
    `${API_BASE}/documents/${documentId}/markdown/upload`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData
    }
  );

  return await response.json();
}

// 管理员：跨知识库查询
async function adminQuery(query, userId = null) {
  const response = await fetch(`${API_BASE}/query/admin`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify({ query, user_id: userId })
  });

  return await response.json();
}
```

---

## 🎯 总结

这套多租户 RAG 知识库方案包含了：

✅ **完整的 Docker 容器化部署方案**（含 Celery Worker）
✅ **本地 LLM 集成**（Ollama + LangChain）
✅ **企业级向量数据库**（Milvus 分区隔离）
✅ **MinerU 高质量 PDF→Markdown 转换**
✅ **多租户数据隔离**（PostgreSQL + Milvus + MinIO）
✅ **灵活的权限控制**（普通用户 vs 管理员）
✅ **清晰的 API 接口设计**
✅ **完整的迁移指南**

### 核心特性

1. **多租户隔离**：每个用户独立知识库，管理员可跨库访问
2. **MinerU 集成**：高质量文档转换，支持用户编辑
3. **异步处理**：Celery 处理长时间任务，提升用户体验
4. **权限矩阵**：细粒度权限控制，满足企业需求
5. **可扩展架构**：支持大量并发用户和文档

现在你可以直接使用这个架构开始实施，或与开发团队沟通具体的功能改进需求。
