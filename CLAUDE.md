# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Multi-Tenant RAG (Retrieval-Augmented Generation) Knowledge Base System** with document management, MinerU-powered Markdown conversion, admin review workflow, and per-user vector search capabilities. Each user has an isolated knowledge base, while administrators can access all users' data.

**Core workflow (Multi-Tenant)**:
- **User**: Upload (PDF/DOCX) → MinerU converts to Markdown → Download & Edit Markdown → Upload edited Markdown → Admin Review → Index to user's Milvus partition → Query own knowledge base
- **Admin**: Review all users' documents → Approve/Reject → Query across any user's knowledge base or all knowledge bases

## Architecture

### Stack
- **Backend**: FastAPI (Python) - `/backend`
- **Frontend**: Static HTML/JS/CSS - `/frontend`
- **Database**: PostgreSQL (metadata, user data, document records with owner_id)
- **Vector DB**: Milvus with per-user partitions (user_1, user_2, etc.)
- **Object Storage**: MinIO with per-user directories (user_{id}/documents/, user_{id}/markdown/)
- **LLM**: Ollama (local LLM for generation and embeddings)
- **Task Queue**: Celery + Redis (for async MinerU document conversion)
- **Document Converter**: MinerU (high-quality PDF→Markdown conversion)

### Service Dependencies
All services run in Docker containers orchestrated by docker-compose:
- `postgres` - PostgreSQL database
- `redis` - Redis cache + Celery broker
- `etcd` - Required by Milvus
- `milvus` - Vector database with multi-tenant partitions
- `minio` - S3-compatible object storage
- `ollama` - Local LLM service
- `backend` - FastAPI application (port 8001→8000)
- `celery_worker` - Celery worker for MinerU conversion tasks
- `frontend` - Nginx serving static files (port 3000)

### Backend Structure

```
backend/
├── main.py                    # FastAPI app entry, lifespan events, CORS
├── alembic/                   # Database migrations
├── app/
│   ├── config.py             # Pydantic settings from .env
│   ├── database.py           # SQLAlchemy engine and session
│   ├── api/                  # FastAPI route handlers
│   │   ├── router.py         # Main router aggregation
│   │   ├── auth.py           # Login, register endpoints
│   │   ├── documents.py      # Upload, Markdown download/upload, list (owner-filtered)
│   │   ├── review.py         # Admin: approve/reject, pending list (all users)
│   │   ├── query.py          # RAG query (user's partition) + admin cross-query
│   │   ├── health.py         # Health check endpoint
│   │   └── deps.py           # Dependency injection (get_db, get_current_user, require_admin)
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── user.py
│   │   ├── document.py       # owner_id, markdown_path, markdown_status fields
│   │   ├── document_chunk.py
│   │   └── review_action.py
│   ├── schemas/              # Pydantic request/response models
│   ├── services/             # Business logic
│   │   ├── auth_service.py       # JWT token generation/validation
│   │   ├── document_parser.py    # PDF/DOCX parsing (may be replaced by MinerU)
│   │   ├── text_splitter.py      # Chunk text for indexing
│   │   ├── embedding_service.py  # Generate embeddings (hash/ollama/sentence-transformers)
│   │   ├── milvus_service.py     # Vector DB operations with partition support
│   │   ├── minio_service.py      # File upload/download with user isolation
│   │   ├── llm_service.py        # Ollama API client
│   │   └── rag_service.py        # RAG workflow: retrieve + generate (partition-aware)
│   └── utils/
│       ├── init_db.py            # Create default admin user
│       └── init_milvus.py        # Create Milvus collections
├── tasks/                     # Celery tasks (NEW)
│   ├── celery_app.py         # Celery application configuration
│   └── mineru_tasks.py       # MinerU PDF→Markdown conversion tasks
```

### Database Schema

**Key Tables**:
- `users`: User accounts (username, hashed_password, role)
- `documents`: Document metadata with multi-tenant support
  - **NEW**: `owner_id` - Foreign key to users table (multi-tenant isolation)
  - **NEW**: `markdown_path` - Path to converted Markdown in MinIO
  - **NEW**: `markdown_status` - Status of MinerU conversion (pending/processing/markdown_ready/failed)
  - **NEW**: `markdown_error` - Error message if conversion failed
  - Existing: filename, status, minio_object, sha256, uploader_id, reviewer_id, timestamps
  - Stores MinIO object paths: `minio_bucket`, `minio_object` (original), `markdown_path` (converted)
  - Tracks document lifecycle with timestamps: `created_at`, `confirmed_at`, `reviewed_at`, `indexed_at`
  - `preview_text` stores first few chunks for UI preview
- `document_chunks`: Text chunks from approved documents (document_id, chunk_index, content, char_count)
  - Created during approval process, before Milvus indexing
  - Used for retrieval alongside Milvus vectors
- `review_actions`: Audit log of approve/reject actions (document_id, reviewer_id, action, reason, timestamp)

**Relationships**:
- Documents have `uploader` (User) and `reviewer` (User) foreign keys
- **Documents have `owner` (User) foreign key for multi-tenant isolation**
- Documents have one-to-many relationship with `document_chunks` (cascade delete)

**Indexes (Important for Multi-Tenant)**:
```sql
CREATE INDEX idx_documents_owner_id ON documents(owner_id);
CREATE INDEX idx_documents_markdown_status ON documents(markdown_status);
CREATE INDEX idx_documents_status_owner ON documents(status, owner_id);
```

### Document Status Flow (Multi-Tenant with MinerU)

Documents transition through states stored in `documents.status` and `markdown_status`:

**Main Status Flow**:
1. `uploaded` - Initial state after upload (triggers MinerU conversion)
2. `confirmed` - User confirmed after reviewing/editing Markdown (optional)
3. `approved` - Admin approved, indexing initiated to user's partition
4. `indexed` - Chunks successfully indexed to user's Milvus partition (terminal success state)
5. `rejected` - Admin rejected (terminal failure state)

**Improved Review Logic**: Admins can approve/reject documents in **both** `uploaded` and `confirmed` states. This allows flexible workflows:
- **Fast-track**: Upload → Admin Review → Approved (skip user confirmation if Markdown editing is not needed)
- **Full workflow**: Upload → User Edits Markdown → Confirmed → Admin Review → Approved

**Markdown Status Flow** (parallel to main status):
1. `pending` - Awaiting MinerU conversion (set on upload)
2. `processing` - MinerU Celery task running
3. `markdown_ready` - Conversion successful, ready for user download/edit
4. `failed` - Conversion failed (check `markdown_error` field)

**Combined Workflow**:
```
Upload → uploaded + markdown_status=pending
       → Celery task triggered
       → markdown_status=processing
       → markdown_status=markdown_ready (user can download/edit)
       → User uploads edited MD → confirmed
       → Admin approves → approved
       → Index to user's Milvus partition → indexed
```

**Note**: The approval endpoint (`POST /api/v1/review/approve/{id}`) sets status to `approved`, then calls `RAGService().index_document()` which:
1. Uses the edited Markdown content (from `markdown_path`) instead of raw PDF text
2. Indexes to the user's partition (`user_{owner_id}`)
3. Updates status to `indexed` upon successful completion

If indexing fails, the document remains in `approved` state. Check backend logs for errors.

The `review_actions` table logs all admin approval/rejection actions.

## Common Commands

### Development Setup

Start all services:
```bash
docker compose up -d --build
```

Check health of all dependencies:
```bash
curl http://localhost:8001/api/v1/health
```

### Backend Development

Run backend locally (outside container):
```bash
cd backend
pip install -r requirements.txt
# Configure .env to point to localhost services
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Run backend tests inside container:
```bash
docker compose exec backend python /scripts/sdk_smoke_test.py --api-url http://localhost:8000/api/v1 --with-pdf --with-reject
```

Access backend container:
```bash
docker compose exec backend bash
```

View backend logs:
```bash
docker compose logs -f backend
```

### Celery Worker Management (NEW)

View Celery worker logs:
```bash
docker compose logs -f celery_worker
```

Restart Celery worker:
```bash
docker compose restart celery_worker
```

Monitor active Celery tasks:
```bash
docker compose exec celery_worker celery -A tasks.celery_app inspect active
```

Check MinerU conversion queue:
```bash
docker compose exec celery_worker celery -A tasks.celery_app inspect reserved
```

Manually trigger MinerU conversion for a document:
```bash
docker compose exec backend python -c "from tasks.mineru_tasks import convert_to_markdown; convert_to_markdown.delay(document_id=1)"
```

### Database Migrations

Create a new migration:
```bash
docker compose exec backend alembic revision --autogenerate -m "description"
```

Apply migrations:
```bash
docker compose exec backend alembic upgrade head
```

Rollback migration:
```bash
docker compose exec backend alembic downgrade -1
```

Access database:
```bash
docker compose exec postgres psql -U admin -d knowledge_base
```

### Ollama Model Management

List installed models:
```bash
docker compose exec ollama ollama list
```

Pull a model (for generation):
```bash
docker compose exec ollama ollama pull qwen2.5:32b
```

Pull embedding model:
```bash
docker compose exec ollama ollama pull nomic-embed-text
```

Test Ollama directly:
```bash
docker compose exec ollama ollama run qwen2.5:32b "Hello"
```

### Milvus Operations (Multi-Tenant)

Access Milvus container:
```bash
docker compose exec milvus bash
```

The Milvus collection is auto-created on backend startup via `init_milvus.py`.

**List all user partitions**:
```bash
docker compose exec backend python -c "from app.services.milvus_service import MilvusService; m=MilvusService(); print(m.collection.partitions)"
```

**Create partition for a new user**:
```bash
docker compose exec backend python -c "from app.services.milvus_service import MilvusService; m=MilvusService(); m.create_partition('user_123')"
```

**Query specific user's partition**:
```bash
docker compose exec backend python -c "
from app.services.milvus_service import MilvusService
m = MilvusService()
# Search in user_1's partition only
results = m.collection.search(
    data=[[0.1, 0.2, ...]],  # query vector
    anns_field='embedding',
    partition_names=['user_1'],
    limit=5
)
print(results)
"
```

Recreate Milvus collection (WARNING: deletes all indexed data and partitions):
```bash
docker compose exec backend python -c "from app.services.milvus_service import MilvusService; m=MilvusService(); m.drop_collection(); m.ensure_collection()"
```

### MinIO Operations

MinIO console (if exposed): `http://localhost:9000` (default not exposed in docker-compose.yml)
Credentials: `minioadmin` / `minioadmin`

Bucket is auto-created on backend startup via `MinioService().ensure_bucket()`.

Download a document's original file from MinIO:
```bash
# Get the minio_object path from database first
docker compose exec postgres psql -U admin -d knowledge_base -c "SELECT id, filename, minio_object FROM documents WHERE id=1;"

# Download using Python (from inside backend container)
docker compose exec backend python -c "from app.services.minio_service import MinioService; content = MinioService().download_bytes('<minio_object>'); open('/tmp/file.pdf', 'wb').write(content)"
```

**Note**: There's currently no API endpoint to download original files. Consider adding `GET /api/v1/documents/{id}/download` if needed.

## Configuration

All configuration is in `.env` (see `.env.example` for template).

### Critical Settings

**Embedding Provider** (`EMBEDDING_PROVIDER`):
- `hash` (default): Fast, zero-dependency, but poor retrieval quality (demo only)
- `ollama`: Use Ollama embeddings API
  - Requires: `docker compose exec ollama ollama pull <model_name>`
  - Model name must match `OLLAMA_EMBEDDING_MODEL` env var (default: `nomic-embed-text`)
  - Ensure embedding dimension matches `EMBEDDING_DIMENSION` (default: 384)
- `sentence_transformers`: Local transformer model (requires `pip install sentence-transformers`)

**Ports**:
- Backend is mapped `8001:8000` on host to avoid conflicts (change in `docker-compose.yml` if needed)
- Frontend is on port `3000`

**Celery Configuration (NEW)**:
- `CELERY_BROKER_URL`: Redis URL for task queue (default: `redis://redis:6379/0`)
- `CELERY_RESULT_BACKEND`: Redis URL for task results (default: `redis://redis:6379/0`)
- Celery worker runs in separate container (`celery_worker`)

**MinerU Configuration (NEW)**:
- MinerU models are cached in Docker volume `mineru_models`
- First conversion will download models (may take time)
- GPU acceleration optional (uncomment GPU config in `docker-compose.yml`)

**Default Admin**:
- Admin credentials are configured via `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`)
- Created automatically on first startup via `create_admin()` in `main.py` lifespan

## Key Implementation Details

### Document Upload Flow (Multi-Tenant with MinerU)
1. User uploads file via `POST /api/v1/documents/upload`
2. File saved to MinIO at `user_{owner_id}/documents/{uuid}/{filename}` (user isolation)
3. Document record created with `owner_id=current_user.id`, `status=uploaded`, `markdown_status=pending`
4. **Celery task triggered**: `convert_to_markdown.delay(document_id)`
5. MinerU converts PDF→Markdown asynchronously:
   - Downloads original file from MinIO
   - Runs MinerU conversion
   - Saves Markdown to MinIO at `user_{owner_id}/markdown/{document_id}.md`
   - Updates `markdown_status=markdown_ready` or `failed`
6. User polls `GET /documents/{id}/status` to check conversion status
7. User downloads Markdown via `GET /documents/{id}/markdown/download`
8. User edits Markdown locally, then uploads via `POST /documents/{id}/markdown/upload`
9. Document status becomes `confirmed` after Markdown upload
10. Admin reviews via `POST /api/v1/review/approve/{id}` or `reject/{id}`
11. On approval:
    - Status set to `approved`
    - Markdown content is loaded from MinIO (not raw PDF text)
    - Text is split into chunks (stored in `document_chunks` table)
    - Chunks are embedded using the configured embedding provider
    - Embeddings are indexed to **user's Milvus partition** (`user_{owner_id}`)
    - Status becomes `indexed`
12. On indexing failure: document remains in `approved` status. Check backend logs for errors.
    Common failures: Milvus connection issues, embedding service errors, partition creation errors.

### RAG Query Flow (Multi-Tenant)
1. User query via `POST /api/v1/query`
2. Query text is embedded using same embedding provider as documents
3. Top-k similar chunks retrieved from **user's Milvus partition only** (`partition_names=[f"user_{current_user.id}"]`)
4. Retrieved chunks + query sent to Ollama LLM
5. LLM generates answer based on context
6. If Ollama model unavailable, falls back to returning raw chunks

**Note**: The default RAG prompt template (`app/utils/prompt_templates.py`) is in Chinese. To customize the prompt language or instructions, modify `RAG_PROMPT_TEMPLATE`.

### Authentication & Multi-Tenant Permissions
- JWT-based authentication
- Tokens obtained via `POST /api/v1/auth/login` or `POST /api/v1/auth/register`
- Token required for most endpoints via `Authorization: Bearer <token>` header
- **Role-based access**: `user` (普通用户) vs `admin` (管理员)

**Permission Matrix**:

| Operation | User | Admin |
|-----------|------|-------|
| Upload documents | ✅ To own library | ✅ To own library |
| List documents | ✅ Own only | ✅ All users (with `?user_id=X`) |
| Download Markdown | ✅ Own only | ✅ Any user's |
| Upload edited Markdown | ✅ Own only | ✅ To any library |
| Review documents | ❌ | ✅ All users' documents |
| Query knowledge base | ✅ Own partition | ✅ Any partition or all (`/query/admin`) |
| Delete documents | ✅ Own only | ✅ Any user's |

**Token Usage Example**:
```bash
# Get token
TOKEN=$(curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"<ADMIN_USERNAME>","password":"<ADMIN_PASSWORD>"}' | jq -r '.access_token')

# Use token in requests
curl http://localhost:8001/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@document.pdf"
```

### Multi-Tenant API Endpoints

**Document Management** (owner-filtered):
- `GET /api/v1/documents` - List user's documents with pagination
  - Query params: `page` (default 1), `page_size` (default 20, max 100), `status_filter` (optional)
  - Users see their own documents; admins see all documents
  - Returns: `{documents: [], total: int, page: int, page_size: int}`
- `GET /api/v1/documents/{id}` - Get document details
- `GET /api/v1/documents/{id}/markdown/status` - Check MinerU conversion status
- `GET /api/v1/documents/{id}/markdown/download` - Download converted Markdown
- `POST /api/v1/documents/{id}/markdown/upload` - Upload edited Markdown
- `DELETE /api/v1/documents/{id}` - Delete a document (with files and vectors)
  - Users can delete their own documents; admins can delete any document
  - Automatically cleans up MinIO files and Milvus vectors
- `POST /api/v1/documents/batch-delete` - Batch delete multiple documents
  - Request body: `{"document_ids": [1, 2, 3]}`
  - Returns: `{"deleted_count": 2, "failed_ids": [3], "message": "..."}`

**Document Review** (admin only):
- `GET /api/v1/review/pending` - Get documents pending review (status: uploaded or confirmed)
- `POST /api/v1/review/approve/{id}` - Approve and index document
- `POST /api/v1/review/reject/{id}` - Reject document with reason
  - Request body: `{"reason": "不符合要求"}`

**Admin Cross-Query**:
- `POST /api/v1/query/admin` - Query specific user's library or all libraries
  ```json
  {
    "query": "Python异步编程",
    "user_id": 123,  // Optional: specific user, omit for all users
    "top_k": 5
  }
  ```

**User Statistics** (admin only):
- `GET /api/v1/users` - List all users
- `GET /api/v1/users/{id}/stats` - User's knowledge base statistics
  ```json
  {
    "user_id": 123,
    "username": "alice",
    "total_documents": 45,
    "indexed_documents": 42,
    "pending_review": 2,
    "rejected": 1,
    "storage_used_mb": 125.3
  }
  ```

### Embedding Service
The `embedding_service.py` supports three providers:
- **hash**: Deterministic hash-based vectors (fast, no dependencies, poor quality)
- **ollama**: Calls Ollama `/api/embeddings` endpoint
- **sentence_transformers**: Local HuggingFace model

Switch via `EMBEDDING_PROVIDER` env var. Dimension configured via `EMBEDDING_DIMENSION` (default 384).

## Testing

Smoke test script at `/scripts/sdk_smoke_test.py`:
- Tests full workflow: health check, login, upload, confirm, approve/reject, query
- Supports `--with-pdf` and `--with-reject` flags

Run inside container:
```bash
docker compose exec backend python /scripts/sdk_smoke_test.py --api-url http://localhost:8000/api/v1 --with-pdf --with-reject
```

## API Documentation

When backend is running:
- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

All API routes are prefixed with `/api/v1` (defined in `app/api/router.py`).

## Common Issues & Troubleshooting

**Ollama model not available**: Query endpoint returns "LLM model not available" and raw chunks. Pull the model specified in `OLLAMA_MODEL` env var.
```bash
docker compose exec ollama ollama pull qwen2.5:32b
```

**Milvus connection errors**: Ensure etcd is healthy. Check `docker compose logs milvus etcd`.
```bash
# Restart Milvus and etcd
docker compose restart etcd milvus
# Wait for healthy status
docker compose ps
```

**Port conflicts**: Backend defaults to host port 8001. Change `docker-compose.yml` `backend.ports` if needed.

**PDF with no text**: Scanned/image PDFs won't extract text without OCR (not implemented). Upload will succeed but preview will be empty or show "未提取到可搜索文本".

**Embedding dimension mismatch**: If changing `EMBEDDING_PROVIDER`, may need to recreate Milvus collection or ensure `EMBEDDING_DIMENSION` matches.
```bash
# Check current Milvus collection schema
docker compose exec backend python -c "from app.services.milvus_service import MilvusService; print(MilvusService().collection.schema)"
```

**Documents stuck in `approved` status**: Indexing failed. Check backend logs:
```bash
docker compose logs backend | grep -i error
# Manually retry indexing for a document
docker compose exec backend python -c "from app.services.rag_service import RAGService; from app.database import SessionLocal; db=SessionLocal(); RAGService(db).index_document(document_id=1)"
```

**Database connection issues**: Verify PostgreSQL is healthy and credentials match `.env`:
```bash
docker compose exec postgres psql -U admin -d knowledge_base -c "SELECT COUNT(*) FROM documents;"
```

**MinIO upload failures**: Check MinIO service is running and bucket exists:
```bash
docker compose logs minio
docker compose exec backend python -c "from app.services.minio_service import MinioService; MinioService().ensure_bucket()"
```

**Frontend can't reach backend**: Ensure CORS_ORIGINS in `.env` includes frontend origin. For development, `["*"]` allows all origins.

**MinerU conversion stuck in `processing`** (NEW): Check Celery worker status:
```bash
docker compose logs celery_worker | grep -i error
# Check active tasks
docker compose exec celery_worker celery -A tasks.celery_app inspect active
# Restart worker
docker compose restart celery_worker
```

**MinerU conversion failed** (NEW): Document has `markdown_status=failed`. Check error:
```bash
docker compose exec postgres psql -U admin -d knowledge_base -c "SELECT id, filename, markdown_error FROM documents WHERE markdown_status='failed';"
# Retry conversion manually
docker compose exec backend python -c "from tasks.mineru_tasks import convert_to_markdown; convert_to_markdown.delay(document_id=1)"
```

**MinerU models not downloading** (NEW): First conversion downloads models (GB-sized):
```bash
# Check download progress in worker logs
docker compose logs -f celery_worker
# Models cached in volume mineru_models
docker volume inspect ragsystem_mineru_models
```

**User can't see their documents** (NEW): Check owner_id filtering:
```bash
docker compose exec postgres psql -U admin -d knowledge_base -c "SELECT id, filename, owner_id, status FROM documents WHERE owner_id=1;"
# Verify user ID in JWT token
docker compose exec backend python -c "import jwt; print(jwt.decode('YOUR_TOKEN', options={'verify_signature': False}))"
```

**Milvus partition not found** (NEW): User partition may not be created:
```bash
# List all partitions
docker compose exec backend python -c "from app.services.milvus_service import MilvusService; print(MilvusService().collection.partitions)"
# Create missing partition
docker compose exec backend python -c "from app.services.milvus_service import MilvusService; MilvusService().create_partition('user_1')"
```

**Admin can't query across users** (NEW): Use admin endpoint, not regular query:
```bash
# Wrong: POST /api/v1/query (only queries admin's own partition)
# Correct: POST /api/v1/query/admin with optional user_id parameter
curl -X POST http://localhost:8001/api/v1/query/admin \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "user_id": null}'  # null = all users
```

## Design Patterns

### Service Layer Pattern
Business logic is in `/app/services/`, route handlers in `/app/api/` are thin and delegate to services.

### Dependency Injection
FastAPI's `Depends()` pattern is used extensively for cross-cutting concerns:
- `get_db()`: Provides SQLAlchemy session (auto-commits/rollbacks)
- `get_current_user()`: Validates JWT token, returns User object (raises 401 if invalid)
- `require_admin()`: Validates user is admin (raises 403 if not admin)

Example usage in route handlers (see `app/api/deps.py` for implementations).

### Startup Initialization
On backend startup (`main.py` lifespan context), the following tasks run sequentially:
1. Database migrations (`_run_migrations()`)
2. MinIO bucket creation (`MinioService().ensure_bucket()`)
3. Milvus collection creation (`init_collections()`)
4. Admin user creation (`create_admin()`)

**Important**: All tasks are wrapped in try/except. Failures log warnings but don't prevent startup. This allows the API to start even if optional services (like Milvus) are temporarily unavailable.

**Note**: On first startup, if tables exist but `alembic_version` is missing, migrations are auto-stamped to `head` without running. This handles pre-existing databases.

### Document State Machine
Document status transitions are enforced in service layer (can't approve a non-confirmed document, etc).

## Useful Database Queries

Check document status distribution:
```sql
SELECT status, COUNT(*) FROM documents GROUP BY status;
```

Find documents stuck in processing:
```sql
SELECT id, filename, status, created_at, reviewed_at
FROM documents
WHERE status = 'approved' AND indexed_at IS NULL
ORDER BY reviewed_at DESC;
```

View recent activity:
```sql
SELECT d.id, d.filename, d.status, u.username as uploader, r.username as reviewer, d.created_at
FROM documents d
LEFT JOIN users u ON d.uploader_id = u.id
LEFT JOIN users r ON d.reviewer_id = r.id
ORDER BY d.created_at DESC LIMIT 10;
```

Check chunk count per document:
```sql
SELECT d.id, d.filename, d.status, COUNT(c.id) as chunk_count
FROM documents d
LEFT JOIN document_chunks c ON d.id = c.document_id
GROUP BY d.id
ORDER BY d.id;
```

## Extending the System

**Adding a new document type**:
1. Extend `document_parser.py` to handle new file extensions
2. Update file validation in `app/api/documents.py` to accept the new extension
3. Test parsing and chunking with sample files

**Custom embedding model**:
1. Add new provider branch in `embedding_service.py`
2. Update `EMBEDDING_PROVIDER` choices in config
3. Ensure `EMBEDDING_DIMENSION` matches the model's output dimension
4. Recreate Milvus collection if dimension changes

**Additional LLM providers**:
1. Create new service class (e.g., `openai_service.py`) similar to `llm_service.py`
2. Modify `rag_service.py` to support multiple providers via config
3. Add provider-specific settings to `.env` and `config.py`

**Multi-tenancy**:
1. Documents already have `uploader_id`. Add filtering in query endpoints
2. Add `user_id` to Milvus metadata when indexing chunks
3. Filter Milvus queries by `user_id` in `rag_service.py`
4. Update review endpoints to only show documents for allowed tenants

**Adding document download endpoint**:
```python
# In app/api/documents.py
@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check permissions (uploader or admin)
    if document.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    content = MinioService().download_bytes(document.minio_object)
    return Response(
        content=content,
        media_type=document.content_type,
        headers={"Content-Disposition": f'attachment; filename="{document.filename}"'}
    )
```

## Frontend Architecture

The frontend is a simple static HTML/JS/CSS application served by Nginx (port 3000).

**Key Files**:
- `index.html`: Single-page app with tabbed interface (Upload, Review, Query)
- `app.js`: Vanilla JavaScript handling API calls and UI updates
- `style.css`: Styling

**Features**:
- JWT token stored in localStorage (key: `kb_token`)
- Auto-detects backend URL based on hostname (e.g., `http://localhost:8001/api/v1`)
- Admin role check: Review tab only visible/enabled for admin users
- Tab persistence: Active tab remembered in session

**API Integration**:
- All API calls include `Authorization: Bearer <token>` header from localStorage
- Token payload decoded client-side to extract username and role
- CORS handled by backend (`CORS_ORIGINS` in `.env`)

**Customization**:
- To change backend URL, modify `API_BASE` in `app.js` line 3
- Default assumes backend on same host at port 8001
- For production, use environment variable or build-time config

## Performance Considerations

**Embedding Generation**:
- `hash` provider: Instant (deterministic hash)
- `ollama` provider: ~100-500ms per chunk depending on model and hardware
- `sentence_transformers`: ~50-200ms per chunk with CPU, faster with GPU

**Document Indexing**:
- Large documents (>100 pages) can take 30+ seconds to index
- Indexing happens synchronously during approval (blocks HTTP response)
- Consider background task queue (Celery) for async indexing if needed

**Milvus Query Performance**:
- Top-k=5 typical response time: 50-200ms
- Collection size impact: Minimal up to 1M vectors, scales well beyond
- Consider index tuning for large collections (IVF_FLAT, HNSW, etc.)

**LLM Generation**:
- Ollama response time varies by model size and context length
- qwen2.5:32b: ~2-10 seconds for typical queries
- Smaller models (7b, 14b): ~0.5-3 seconds
- Consider streaming responses for better UX

**Database Queries**:
- Most queries are simple lookups by ID or status (fast with indexes)
- Document listing by status should have index on `status` column (already exists)
- Consider pagination for large document lists (not currently implemented)

**File Storage**:
- MinIO handles large files efficiently
- Consider object lifecycle policies for old/rejected documents
- Monitor bucket size and implement cleanup for rejected files after retention period
