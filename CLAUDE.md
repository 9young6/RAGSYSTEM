# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a RAG (Retrieval-Augmented Generation) Knowledge Base System with document management, admin review workflow, and vector search capabilities. The system allows users to upload PDF/DOCX documents, which go through a confirmation and approval process before being indexed into Milvus for semantic search and LLM-powered querying.

**Core workflow**: Upload (PDF/DOCX) → Parse & Preview → User Confirmation → Admin Review (approve/reject) → Index to Milvus → Query with Ollama

## Architecture

### Stack
- **Backend**: FastAPI (Python) - `/backend`
- **Frontend**: Static HTML/JS/CSS - `/frontend`
- **Database**: PostgreSQL (metadata, user data, document records)
- **Vector DB**: Milvus (document embeddings and chunks)
- **Object Storage**: MinIO (original document files)
- **LLM**: Ollama (local LLM for generation and embeddings)
- **Caching**: Redis (optional, configured but not heavily used)

### Service Dependencies
All services run in Docker containers orchestrated by docker-compose:
- `postgres` - PostgreSQL database
- `redis` - Redis cache
- `etcd` - Required by Milvus
- `milvus` - Vector database
- `minio` - S3-compatible object storage
- `ollama` - Local LLM service
- `backend` - FastAPI application (port 8001→8000)
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
│   │   ├── documents.py      # Upload, confirm, list documents
│   │   ├── review.py         # Admin: approve/reject, pending list
│   │   ├── query.py          # RAG query endpoint
│   │   ├── health.py         # Health check endpoint
│   │   └── deps.py           # Dependency injection (get_db, get_current_user, etc.)
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── user.py
│   │   ├── document.py
│   │   ├── document_chunk.py
│   │   └── review_action.py
│   ├── schemas/              # Pydantic request/response models
│   ├── services/             # Business logic
│   │   ├── auth_service.py       # JWT token generation/validation
│   │   ├── document_parser.py    # PDF/DOCX parsing
│   │   ├── text_splitter.py      # Chunk text for indexing
│   │   ├── embedding_service.py  # Generate embeddings (hash/ollama/sentence-transformers)
│   │   ├── milvus_service.py     # Vector DB operations
│   │   ├── minio_service.py      # File upload/download
│   │   ├── llm_service.py        # Ollama API client
│   │   └── rag_service.py        # RAG workflow: retrieve + generate
│   └── utils/
│       ├── init_db.py            # Create default admin user
│       └── init_milvus.py        # Create Milvus collections
```

### Database Schema

**Key Tables**:
- `users`: User accounts (username, hashed_password, role)
- `documents`: Document metadata (filename, status, minio_object, sha256, uploader_id, reviewer_id, timestamps)
  - Stores MinIO object path (`minio_bucket`, `minio_object`) for original file
  - Tracks document lifecycle with timestamps: `created_at`, `confirmed_at`, `reviewed_at`, `indexed_at`
  - `preview_text` stores first few chunks for UI preview
- `document_chunks`: Text chunks from approved documents (document_id, chunk_index, content, char_count)
  - Created during approval process, before Milvus indexing
  - Used for retrieval alongside Milvus vectors
- `review_actions`: Audit log of approve/reject actions (document_id, reviewer_id, action, reason, timestamp)

**Relationships**:
- Documents have `uploader` (User) and `reviewer` (User) foreign keys
- Documents have one-to-many relationship with `document_chunks` (cascade delete)

### Document Status Flow

Documents transition through states stored in `documents.status`:
1. `uploaded` - Initial state after upload
2. `confirmed` - User confirmed the preview
3. `approved` - Admin approved, indexing initiated
4. `indexed` - Chunks successfully indexed to Milvus (terminal success state)
5. `rejected` - Admin rejected (terminal failure state)

**Note**: The approval endpoint (`POST /api/v1/review/approve/{id}`) sets status to `approved`, then calls `RAGService().index_document()` which updates it to `indexed` upon successful completion. If indexing fails, the document remains in `approved` state. Check backend logs for errors.

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

### Milvus Operations

Access Milvus container:
```bash
docker compose exec milvus bash
```

The Milvus collection is auto-created on backend startup via `init_milvus.py`.

Recreate Milvus collection (WARNING: deletes all indexed data):
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

**Default Admin**:
- Username: `admin`
- Password: `admin123`
- Created automatically on first startup via `create_admin()` in `main.py` lifespan

## Key Implementation Details

### Document Upload Flow
1. User uploads file via `POST /api/v1/documents/upload`
2. File saved to MinIO, parsed (PDF/DOCX), text extracted
3. Text split into chunks, preview returned to user
4. Document saved with status `uploaded`
5. User confirms via `POST /api/v1/documents/confirm/{id}` → status becomes `confirmed`
6. Admin reviews via `POST /api/v1/review/approve/{id}` or `reject/{id}`
7. On approval:
   - Status set to `approved`
   - Full document text is parsed from MinIO
   - Text is split into chunks (stored in `document_chunks` table)
   - Chunks are embedded using the configured embedding provider
   - Embeddings are indexed to Milvus (with document_id and chunk_index as metadata)
   - Status becomes `indexed`
8. On indexing failure: document remains in `approved` status. Check backend logs for errors.
   Common failures: Milvus connection issues, embedding service errors, file parsing errors.

### RAG Query Flow
1. User query via `POST /api/v1/query`
2. Query text is embedded using same embedding provider as documents
3. Top-k similar chunks retrieved from Milvus
4. Retrieved chunks + query sent to Ollama LLM
5. LLM generates answer based on context
6. If Ollama model unavailable, falls back to returning raw chunks

**Note**: The default RAG prompt template (`app/utils/prompt_templates.py`) is in Chinese. To customize the prompt language or instructions, modify `RAG_PROMPT_TEMPLATE`.

### Authentication
- JWT-based authentication
- Tokens obtained via `POST /api/v1/auth/login` or `POST /api/v1/auth/register`
- Token required for most endpoints via `Authorization: Bearer <token>` header
- Admin-only endpoints require `role=admin` in user record

**Token Usage Example**:
```bash
# Get token
TOKEN=$(curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r '.access_token')

# Use token in requests
curl http://localhost:8001/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@document.pdf"
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
