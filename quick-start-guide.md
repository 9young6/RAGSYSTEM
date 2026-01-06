# 快速部署与使用指南

## 📦 完整的一键部署方案

### 前置要求
- Docker >= 20.10
- Docker Compose >= 2.0
- 4GB+ 内存
- 20GB+ 磁盘空间（包含LLM模型）

---

## 🚀 方案1：最小化快速启动（推荐新手）

### Step 1: 准备项目结构
```bash
mkdir knowledge-base-system && cd knowledge-base-system

# 创建目录结构
mkdir -p backend/app/{api,services,utils,models,schemas} frontend src docker

# 创建必要文件
touch docker-compose.yml .env requirements.txt Dockerfile
```

### Step 2: 使用官方 docker-compose.yml
```yaml
# docker-compose.yml
version: '3.8'

services:
  # Redis缓存
  redis:
    image: redis:7-alpine
    container_name: kb_redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - kb_network

  # PostgreSQL数据库
  postgres:
    image: postgres:15-alpine
    container_name: kb_postgres
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: secure_password_2024
      POSTGRES_DB: knowledge_base
      POSTGRES_INITDB_ARGS: "-c max_connections=200"
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U admin -d knowledge_base"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - kb_network

  # etcd (Milvus依赖)
  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    container_name: kb_etcd
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
    ports:
      - "2379:2379"
    volumes:
      - etcd_data:/etcd
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls=http://0.0.0.0:2379 --data-dir /etcd
    healthcheck:
      test: ["CMD", "etcdctl", "--endpoints=localhost:2379", "endpoint", "health"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - kb_network

  # Milvus向量数据库
  milvus:
    image: milvusdb/milvus:latest
    container_name: kb_milvus
    environment:
      COMMON_STORAGETYPE: local
    depends_on:
      etcd:
        condition: service_healthy
    ports:
      - "19530:19530"
      - "9091:9091"
    volumes:
      - milvus_data:/var/lib/milvus
    command: milvus run standalone
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      timeout: 10s
      retries: 5
    networks:
      - kb_network

  # MinIO文件存储
  minio:
    image: minio/minio:latest
    container_name: kb_minio
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
      interval: 30s
      timeout: 10s
      retries: 5
    networks:
      - kb_network

  # Ollama本地LLM服务
  ollama:
    image: ollama/ollama:latest
    container_name: kb_ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0:11434
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 5
    networks:
      - kb_network
    # 如果有GPU，取消注释下面的配置
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]

  # FastAPI后端服务
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: kb_backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://admin:secure_password_2024@postgres:5432/knowledge_base
      - MILVUS_HOST=milvus
      - MILVUS_PORT=19530
      - REDIS_URL=redis://redis:6379
      - OLLAMA_BASE_URL=http://ollama:11434
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=minioadmin
      - MINIO_SECRET_KEY=minioadmin
      - DEBUG=False
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      milvus:
        condition: service_healthy
      ollama:
        condition: service_healthy
    volumes:
      - ./backend:/app
    working_dir: /app
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    networks:
      - kb_network

  # Vue3前端服务
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: kb_frontend
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://localhost:8000
      - VITE_API_BASE=/api/v1
    depends_on:
      - backend
    volumes:
      - ./frontend:/app
      - /app/node_modules
    command: npm run dev
    networks:
      - kb_network

volumes:
  postgres_data:
  redis_data:
  milvus_data:
  etcd_data:
  minio_data:
  ollama_data:

networks:
  kb_network:
    driver: bridge
```

### Step 3: 创建 .env 文件
```env
# .env
# ============ 数据库配置 ============
DB_USER=admin
DB_PASSWORD=secure_password_2024
DB_HOST=postgres
DB_PORT=5432
DB_NAME=knowledge_base
DATABASE_URL=postgresql://admin:secure_password_2024@postgres:5432/knowledge_base

# ============ Milvus配置 ============
MILVUS_HOST=milvus
MILVUS_PORT=19530
MILVUS_COLLECTION_NAME=knowledge_base

# ============ Redis配置 ============
REDIS_URL=redis://redis:6379
REDIS_HOST=redis
REDIS_PORT=6379

# ============ Ollama配置 ============
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:32b
OLLAMA_TEMPERATURE=0.7

# ============ MinIO配置 ============
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=knowledge-base
MINIO_USE_SSL=false

# ============ 应用配置 ============
APP_NAME=Knowledge Base Management System
DEBUG=False
LOG_LEVEL=INFO
CORS_ORIGINS=["*"]

# ============ 文档处理配置 ============
CHUNK_SIZE=512
CHUNK_OVERLAP=50
MAX_FILE_SIZE=52428800

# ============ 向量模型配置 ============
EMBEDDING_MODEL=sentence-transformers/paraphrase-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
```

### Step 4: 创建后端Dockerfile
```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动应用
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Step 5: 创建前端Dockerfile
```dockerfile
# frontend/Dockerfile
FROM node:18-alpine AS builder

WORKDIR /app

COPY package*.json ./

RUN npm install -i https://registry.npmmirror.com

COPY . .

RUN npm run build

# Production image
FROM node:18-alpine

WORKDIR /app

RUN npm install -g vite

COPY --from=builder /app/dist ./dist
COPY package*.json ./

RUN npm install -i https://registry.npmmirror.com

EXPOSE 3000

CMD ["npm", "run", "preview"]
```

### Step 6: 启动所有服务
```bash
# 构建镜像
docker-compose build

# 启动容器（后台运行）
docker-compose up -d

# 查看日志
docker-compose logs -f

# 等待所有服务就绪（约2-5分钟）
```

---

## 🔧 初始化配置

### Step 1: 初始化数据库
```bash
# 进入后端容器
docker-compose exec backend bash

# 运行迁移脚本
alembic upgrade head

# 创建管理员用户
python -c "from app.utils.init_db import create_admin; create_admin()"

# 退出容器
exit
```

### Step 2: 下载LLM模型
```bash
# 拉取llama2模型（约3.5GB）
docker-compose exec ollama ollama pull qwen2.5:32b

# 或使用更轻量的mistral模型（约4GB）
docker-compose exec ollama ollama pull mistral

# 或使用更轻量的neural-chat模型（~5GB）
docker-compose exec ollama ollama pull neural-chat

# 查看已安装的模型
docker-compose exec ollama ollama list
```

### Step 3: 初始化Milvus集合
```bash
# 进入后端容器
docker-compose exec backend python

# 运行初始化脚本
from app.utils.init_milvus import init_collections
init_collections()
exit()
```

---

## 🌐 访问应用

| 服务 | 地址 | 用途 |
|------|------|------|
| **前端应用** | http://localhost:3000 | 用户界面 |
| **API文档** | http://localhost:8000/docs | FastAPI Swagger文档 |
| **API文档(ReDoc)** | http://localhost:8000/redoc | 另一种文档格式 |
| **MinIO控制台** | http://localhost:9001 | 文件管理 |
| **Postgres** | localhost:5432 | 数据库连接 |
| **Milvus** | localhost:19530 | 向量数据库连接 |
| **Ollama API** | http://localhost:11434 | LLM API |
| **Redis** | localhost:6379 | 缓存服务 |

### 默认登录凭证
```
前端管理员账号: 见 .env（ADMIN_USERNAME / ADMIN_PASSWORD）
MinIO账号: minioadmin / minioadmin
```

---

## 📝 常用命令

### 查看服务状态
```bash
# 查看所有容器状态
docker-compose ps

# 查看特定容器日志
docker-compose logs backend
docker-compose logs ollama

# 实时查看所有日志
docker-compose logs -f
```

### 重启服务
```bash
# 重启单个服务
docker-compose restart backend

# 重启所有服务
docker-compose restart

# 停止所有服务
docker-compose stop

# 启动所有服务
docker-compose start

# 完全清理并重启
docker-compose down -v
docker-compose up -d
```

### 进入容器
```bash
# 进入后端容器
docker-compose exec backend bash

# 进入数据库
docker-compose exec postgres psql -U admin -d knowledge_base

# 进入Redis
docker-compose exec redis redis-cli
```

### 查看资源使用
```bash
docker stats
```

---

## 🧪 测试API

### 使用curl测试上传文档
```bash
# 上传PDF文件
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@path/to/document.pdf"

# 上传DOCX文件
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@path/to/document.docx"
```

### 使用Python测试查询
```python
import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

# 查询知识库
def query_kb(query_text):
    response = requests.post(
        f"{BASE_URL}/query",
        headers={"Authorization": "Bearer YOUR_TOKEN"},
        json={
            "query": query_text,
            "top_k": 5,
            "model": "qwen2.5:32b",
            "temperature": 0.7
        }
    )
    return response.json()

# 测试
result = query_kb("什么是Python异步编程？")
print(json.dumps(result, ensure_ascii=False, indent=2))
```

### 使用Postman导入API
```json
// 创建 postman_collection.json
{
  "info": {
    "name": "Knowledge Base API",
    "version": "1.0.0"
  },
  "item": [
    {
      "name": "Upload Document",
      "request": {
        "method": "POST",
        "url": "http://localhost:8000/api/v1/documents/upload"
      }
    },
    {
      "name": "Query KB",
      "request": {
        "method": "POST",
        "url": "http://localhost:8000/api/v1/query",
        "body": {
          "mode": "raw",
          "raw": "{\"query\": \"your query\", \"top_k\": 5}"
        }
      }
    }
  ]
}
```

---

## 🐛 常见问题排查

### 问题1: Ollama模型加载失败
```bash
# 查看ollama日志
docker-compose logs ollama

# 检查ollama是否运行
curl http://localhost:11434/api/tags

# 手动拉取模型
docker-compose exec ollama ollama pull qwen2.5:32b

# 如果内存不足，尝试更小的模型
docker-compose exec ollama ollama pull orca-mini
```

### 问题2: Milvus连接错误
```bash
# 检查milvus健康状态
curl http://localhost:9091/healthz

# 查看milvus日志
docker-compose logs milvus

# 重启milvus
docker-compose restart milvus
```

### 问题3: 数据库连接失败
```bash
# 检查postgres是否运行
docker-compose exec postgres pg_isready -U admin

# 查看数据库日志
docker-compose logs postgres

# 重置数据库
docker-compose exec postgres psql -U admin -c "DROP DATABASE knowledge_base; CREATE DATABASE knowledge_base;"
```

### 问题4: 内存不足
```bash
# 查看docker内存使用
docker stats

# 增加docker分配的内存（在Docker Desktop设置中）
# 或删除不需要的镜像
docker image prune -a

# 移除未使用的卷
docker volume prune
```

### 问题5: 端口冲突
```bash
# 查看占用的端口
lsof -i :8000
lsof -i :3000

# 修改docker-compose.yml中的端口映射
# 例如改为 "8001:8000"
```

---

## 🚢 生产部署建议

### 1. 安全加固
```yaml
# docker-compose-prod.yml 示例
services:
  postgres:
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}  # 使用环境变量
    ports: []  # 不暴露端口，仅容器内通信
    
  backend:
    environment:
      - CORS_ORIGINS=["https://yourdomain.com"]
      - DEBUG=False
    restart: always
```

### 2. 日志和监控
```bash
# 配置日志驱动
# docker-compose.yml
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 3. Kubernetes部署
```bash
# 将docker-compose转换为kubernetes
kompose convert -f docker-compose.yml -o ./k8s/

# 部署到集群
kubectl apply -f ./k8s/
```

### 4. 备份策略
```bash
# 定期备份数据库
docker-compose exec postgres pg_dump -U admin knowledge_base > backup.sql

# 备份Milvus数据
docker exec kb_milvus tar czf /var/lib/milvus/backup.tar.gz /var/lib/milvus

# 定时备份脚本
0 2 * * * /path/to/backup.sh
```

---

## 📚 核心文件生成模板

### 后端主文件: main.py
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    logger.info("Knowledge Base System starting...")
    yield
    # 关闭
    logger.info("Knowledge Base System shutting down...")

app = FastAPI(
    title="知识库管理系统",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "ok", "message": "Knowledge Base API v1.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 前端主文件: App.vue
```vue
<template>
  <div id="app" class="app-container">
    <el-container>
      <el-header height="60px">
        <div class="header-content">
          <h1>📚 知识库管理系统</h1>
          <div class="user-info">
            <span>{{ currentUser }}</span>
            <el-button type="text" @click="logout">退出</el-button>
          </div>
        </div>
      </el-header>
      
      <el-container>
        <el-aside width="200px">
          <el-menu default-active="1">
            <el-menu-item index="1" @click="currentPage = 'upload'">
              📤 上传文档
            </el-menu-item>
            <el-menu-item index="2" @click="currentPage = 'review'">
              ✅ 内容审核
            </el-menu-item>
            <el-menu-item index="3" @click="currentPage = 'query'">
              🔍 知识库查询
            </el-menu-item>
          </el-menu>
        </el-aside>
        
        <el-main>
          <component :is="currentPage + 'Page'" />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import UploadPage from './pages/Upload.vue'
import ReviewPage from './pages/Review.vue'
import QueryPage from './pages/Query.vue'

const currentPage = ref('upload')
const currentUser = ref('Admin')

const logout = () => {
  // 登出逻辑
}
</script>

<style scoped>
.app-container {
  min-height: 100vh;
}
.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 100%;
}
</style>
```

---

## ✅ 验收清单

启动后请检查以下项：

- [ ] 所有容器已启动：`docker-compose ps` 显示全部UP
- [ ] 前端可访问：http://localhost:3000
- [ ] API文档可访问：http://localhost:8000/docs
- [ ] 数据库已初始化：可连接到PostgreSQL
- [ ] 模型已下载：Ollama显示已安装的模型
- [ ] 向量库已初始化：Milvus集合已创建
- [ ] 文件上传正常：可上传PDF/DOCX
- [ ] 管理员审核功能可用
- [ ] 查询功能返回正常结果

---

## 🎓 下一步学习

1. **自定义LLM Prompt**
   - 编辑 `backend/app/utils/prompt_templates.py`
   - 调整不同场景的提示词

2. **集成企业认证**
   - 配置 LDAP/AD 用户系统
   - 实现单点登录 (SSO)

3. **性能优化**
   - 添加Nginx反向代理
   - 配置Elasticsearch日志聚合
   - 实现Prometheus监控

4. **功能扩展**
   - 支持更多文档格式（Excel, PPT等）
   - 多语言支持
   - 文档版本管理

祝您部署顺利！有任何问题可以查看详细架构文档。
