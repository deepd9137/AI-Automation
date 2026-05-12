# Phase 5 — RAG System (Document Intelligence)

## Objectives
Build the complete Retrieval-Augmented Generation pipeline: document ingestion, chunking, embedding, vector storage, and context-aware retrieval. Admins upload documents; the system makes them queryable within minutes.

## Dependencies
- Phase 1–3 (DB, auth, documents table)
- Phase 4 (AI client, embedding service)

## Estimated Duration
3–4 days

---

## Deliverables

| # | Deliverable | Done When |
|---|---|---|
| 1 | `POST /documents/upload` — accepts PDF, DOCX, TXT, FAQ, web | File stored, background processing job queued |
| 2 | Ingestion pipeline runs as background task | Document status transitions: `pending → processing → ready` |
| 3 | ChromaDB collection per org | Chunks stored with metadata, org-isolated |
| 4 | `retrieve(query, org_id)` returns ranked chunks | Top-K results with similarity scores |
| 5 | VectorStore abstraction interface | Swapping to Pinecone requires only a new adapter class |
| 6 | Retrieval used in chat (Phase 6 hook) | RAG context injected into LLM system prompt |
| 7 | `GET /documents` — list with status | Frontend shows processing state |
| 8 | `DELETE /documents/{id}` — removes vectors + DB record | Clean teardown |

---

## Overall RAG Flow

```
Admin uploads file
       │
       ▼
File saved to storage (local/S3)
       │
       ▼
Background task: DocumentIngestionPipeline
       │
       ├─ 1. Parse file → raw text
       ├─ 2. Clean & normalize text
       ├─ 3. Chunk text (recursive character splitter)
       ├─ 4. Generate embeddings for each chunk (OpenAI)
       ├─ 5. Upsert vectors into ChromaDB (collection: org_{org_id})
       ├─ 6. Save embeddings_metadata to PostgreSQL
       └─ 7. Mark document status = "ready"

User asks question
       │
       ▼
RetrievalService.retrieve(query, org_id)
       │
       ├─ 1. Embed query
       ├─ 2. ChromaDB semantic search (top 5 chunks)
       ├─ 3. Rerank by score threshold (≥ 0.75)
       └─ 4. Return [{chunk_text, doc_id, score, filename}]

LLM called with:
  - system prompt (rendered with business_name)
  - retrieved chunks as context block
  - conversation history (last N turns)
  - user question
```

---

## Architecture

### Files to Create
```
backend/
├── rag/
│   ├── __init__.py
│   ├── pipeline.py         # DocumentIngestionPipeline
│   ├── chunker.py          # text splitting strategies
│   ├── parser.py           # PDF/DOCX/TXT/web text extraction
│   ├── vector_store.py     # VectorStore interface + ChromaDB adapter
│   └── retriever.py        # RetrievalService
├── tasks/
│   └── ingestion_task.py   # async background task wrapper
└── routes/
    └── documents.py
```

---

## Document Parser (`backend/rag/parser.py`)

```python
from pathlib import Path
import fitz                  # PyMuPDF
from docx import Document as DocxDocument
from bs4 import BeautifulSoup

def parse_file(file_path: str, file_type: str) -> str:
    match file_type:
        case "pdf":
            return _parse_pdf(file_path)
        case "docx":
            return _parse_docx(file_path)
        case "txt" | "faq":
            return Path(file_path).read_text(encoding="utf-8")
        case "web":
            return _parse_html(file_path)
        case _:
            raise ValueError(f"Unsupported file type: {file_type}")

def _parse_pdf(path: str) -> str:
    doc = fitz.open(path)
    return "\n".join(page.get_text() for page in doc)

def _parse_docx(path: str) -> str:
    doc = DocxDocument(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

def _parse_html(path: str) -> str:
    html = Path(path).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml").get_text(separator="\n", strip=True)
```

---

## Chunking Strategy (`backend/rag/chunker.py`)

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

CHUNK_SIZE = 512        # tokens
CHUNK_OVERLAP = 64      # token overlap for context continuity

def chunk_text(text: str, metadata: dict) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", "? ", "! ", " ", ""],
    )
    chunks = splitter.split_text(text)
    return [
        {
            "text": chunk,
            "index": i,
            "metadata": {**metadata, "chunk_index": i},
        }
        for i, chunk in enumerate(chunks)
    ]
```

**Why Recursive Character Splitter?**
- Respects paragraph → sentence → word hierarchy.
- 64-token overlap ensures context sentences aren't cut in half.
- 512 tokens fits 2× within GPT-4o's context window per retrieved chunk.

---

## VectorStore Abstraction (`backend/rag/vector_store.py`)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class SearchResult:
    chunk_text: str
    vector_id: str
    score: float
    metadata: dict

class VectorStore(ABC):
    @abstractmethod
    async def upsert(self, org_id: str, chunks: list[dict]) -> list[str]: ...

    @abstractmethod
    async def search(self, org_id: str, query_vector: list[float], top_k: int = 5) -> list[SearchResult]: ...

    @abstractmethod
    async def delete_by_document(self, org_id: str, document_id: str) -> None: ...


class ChromaDBStore(VectorStore):
    def __init__(self, persist_dir: str):
        import chromadb
        self._client = chromadb.PersistentClient(path=persist_dir)

    def _collection(self, org_id: str):
        return self._client.get_or_create_collection(
            name=f"org_{org_id}",
            metadata={"hnsw:space": "cosine"},
        )

    async def upsert(self, org_id: str, chunks: list[dict]) -> list[str]:
        col = self._collection(org_id)
        ids = [c["metadata"]["vector_id"] for c in chunks]
        col.upsert(
            ids=ids,
            documents=[c["text"] for c in chunks],
            embeddings=[c["embedding"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks],
        )
        return ids

    async def search(self, org_id: str, query_vector: list[float], top_k: int = 5) -> list[SearchResult]:
        col = self._collection(org_id)
        results = col.query(query_embeddings=[query_vector], n_results=top_k)
        return [
            SearchResult(
                chunk_text=results["documents"][0][i],
                vector_id=results["ids"][0][i],
                score=1 - results["distances"][0][i],  # cosine distance → similarity
                metadata=results["metadatas"][0][i],
            )
            for i in range(len(results["ids"][0]))
        ]

    async def delete_by_document(self, org_id: str, document_id: str) -> None:
        col = self._collection(org_id)
        col.delete(where={"document_id": document_id})
```

**Pinecone Adapter** (future): Implement `PineconeStore(VectorStore)` — switch via `settings.VECTOR_STORE_BACKEND = "pinecone"`.

---

## Ingestion Pipeline (`backend/rag/pipeline.py`)

```python
import uuid
from backend.rag.parser import parse_file
from backend.rag.chunker import chunk_text
from backend.ai.embeddings import get_embedding
from backend.rag.vector_store import ChromaDBStore
from backend.repositories.document_repo import update_document_status, save_embeddings_metadata
from backend.core.logging import logger

class DocumentIngestionPipeline:
    def __init__(self, vector_store: ChromaDBStore):
        self.vs = vector_store

    async def run(self, document_id: str, org_id: str, file_path: str, file_type: str, db) -> None:
        try:
            await update_document_status(db, document_id, "processing")

            # 1. Parse
            raw_text = parse_file(file_path, file_type)

            # 2. Chunk
            chunks = chunk_text(raw_text, metadata={"document_id": document_id, "org_id": org_id})

            # 3. Embed (batched to avoid rate limits)
            BATCH_SIZE = 20
            enriched = []
            for i in range(0, len(chunks), BATCH_SIZE):
                batch = chunks[i:i + BATCH_SIZE]
                for chunk in batch:
                    vec_id = str(uuid.uuid4())
                    embedding = await get_embedding(chunk["text"])
                    chunk["embedding"] = embedding
                    chunk["metadata"]["vector_id"] = vec_id
                    enriched.append(chunk)

            # 4. Upsert to vector store
            await self.vs.upsert(org_id, enriched)

            # 5. Persist metadata to PostgreSQL
            await save_embeddings_metadata(db, document_id, org_id, enriched)

            # 6. Mark ready
            await update_document_status(db, document_id, "ready", chunk_count=len(enriched))
            logger.info("ingestion_complete", document_id=document_id, chunks=len(enriched))

        except Exception as e:
            logger.error("ingestion_failed", document_id=document_id, error=str(e))
            await update_document_status(db, document_id, "failed", error_message=str(e))
            raise
```

---

## Retrieval Service (`backend/rag/retriever.py`)

```python
from backend.ai.client import ai_client
from backend.rag.vector_store import VectorStore, SearchResult

SIMILARITY_THRESHOLD = 0.75
TOP_K = 5

class RetrievalService:
    def __init__(self, vector_store: VectorStore):
        self.vs = vector_store

    async def retrieve(self, query: str, org_id: str) -> list[SearchResult]:
        query_vector = await ai_client.embed(query)
        results = await self.vs.search(org_id, query_vector, top_k=TOP_K)
        filtered = [r for r in results if r.score >= SIMILARITY_THRESHOLD]
        return filtered

    def build_context_block(self, results: list[SearchResult]) -> str:
        if not results:
            return ""
        sections = []
        for i, r in enumerate(results, 1):
            doc_name = r.metadata.get("filename", "Document")
            sections.append(f"[Source {i}: {doc_name}]\n{r.chunk_text}")
        return "\n\n---\n\n".join(sections)

    @property
    def has_no_context(self) -> bool:
        return False   # checked per-query
```

**Fallback Logic**: if `retrieve()` returns empty list, the chat service uses the fallback response template instead of calling the LLM.

---

## Document Upload API (`backend/routes/documents.py`)

```
POST   /api/v1/documents/upload
  - multipart/form-data: file
  - Auth: org_admin or agent
  - Max file size: 20 MB
  - Returns: { document_id, status: "pending" }
  - Triggers background ingestion task

GET    /api/v1/documents
  - Returns: [{ id, filename, status, chunk_count, created_at }]

DELETE /api/v1/documents/{id}
  - Removes from ChromaDB + soft-deletes in PostgreSQL

GET    /api/v1/documents/{id}/status
  - Polling endpoint: { status, chunk_count, error_message }
```

### File Security Rules
1. Validate MIME type server-side (not just file extension).
2. Scan file content for embedded scripts before parsing (use `python-magic`).
3. Store files in `storage/{org_id}/{uuid}.{ext}` — never expose original filename in path.
4. Max 20 MB per file, 500 MB total storage per org (free plan).

---

## Metadata Schema in ChromaDB

Each vector stored with:
```json
{
  "document_id": "uuid",
  "org_id": "uuid",
  "filename": "pricing.pdf",
  "file_type": "pdf",
  "chunk_index": 3,
  "vector_id": "uuid"
}
```

This metadata enables:
- Filtering by document (`where={"document_id": "..."}`)
- Displaying source citations in chat UI
- Deleting all chunks when document is removed

---

## Validation Checklist

- [ ] PDF with 50 pages ingests, chunks correctly, `status = "ready"` within 60s
- [ ] DOCX with tables parsed (table text preserved, not corrupted)
- [ ] Duplicate upload of same filename creates new document (not overwrite)
- [ ] `retrieve("pricing question", org_id_A)` does NOT return results from org_id_B
- [ ] Low-relevance query (score < 0.75) returns empty results → fallback triggered
- [ ] Deleting a document removes all its vectors from ChromaDB
- [ ] 21 MB file upload returns `413 Payload Too Large`
- [ ] Non-PDF/DOCX/TXT file returns `415 Unsupported Media Type`

---

## Performance Targets

| Operation | Target |
|---|---|
| Ingestion (10-page PDF) | < 30 seconds |
| Embedding a 512-token chunk | < 200ms |
| Vector search (top 5) | < 100ms |
| End-to-end RAG answer | < 3 seconds |

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| ChromaDB not production-grade at scale | Abstraction allows Pinecone swap; add at Phase 11 |
| Embedding cost on large uploads | Batch to 20 chunks per API call; track cost in token_usage |
| Corrupted PDF blocks ingestion | Catch parse errors, set `status=failed`, notify admin |
| Long ingestion blocks request thread | All ingestion runs in `BackgroundTasks` or Celery worker |

## Rollback Strategy
Delete vectors from ChromaDB collection + run `alembic downgrade` to drop `embeddings_metadata` and reset `documents.status`. Documents themselves (files) remain in storage.

---

## Git Workflow

### Branch
```bash
git checkout develop
git pull
git checkout -b feature/phase-5-rag-system
```

### Commit Checkpoints

```bash
# After document parser (PDF, DOCX, TXT, HTML)
git add backend/rag/parser.py
git commit -m "feat(rag): add document parser for pdf, docx, txt, and web formats"

# After chunking strategy
git add backend/rag/chunker.py
git commit -m "feat(rag): add recursive character text splitter with 512-token chunks"

# After VectorStore abstraction + ChromaDB adapter
git add backend/rag/vector_store.py
git commit -m "feat(rag): add VectorStore interface and ChromaDB adapter with org isolation"

# After ingestion pipeline
git add backend/rag/pipeline.py backend/tasks/ingestion_task.py
git commit -m "feat(rag): add DocumentIngestionPipeline with background task processing"

# After retrieval service
git add backend/rag/retriever.py
git commit -m "feat(rag): add RetrievalService with similarity threshold filtering"

# After document upload + management API
git add backend/routes/documents.py backend/repositories/document_repo.py
git commit -m "feat(rag): add document upload, list, status, and delete endpoints"
```

### Test Before Merging
```bash
# Upload a test PDF and verify end-to-end ingestion
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@tests/fixtures/sample.pdf"

# Poll status until "ready"
curl http://localhost:8000/api/v1/documents/{id}/status \
  -H "Authorization: Bearer $TOKEN"

# Run all tests
pytest backend/tests/test_rag.py -v
```

### Merge to Develop
```bash
git push -u origin feature/phase-5-rag-system

gh pr create \
  --title "feat: Phase 5 — RAG System" \
  --body "Document ingestion pipeline, chunking, ChromaDB vector store (Pinecone-ready), retrieval service. Upload-to-ready tested end-to-end." \
  --base develop
```

---

## Definition of Done

Phase 5 is **complete** when every item below is checked.

### Code Quality
- [ ] `VectorStore` is an abstract class — `ChromaDBStore` is a concrete adapter, not the only path
- [ ] Ingestion runs in `BackgroundTasks` — never blocks the HTTP response
- [ ] File type validated server-side using MIME (not just extension)
- [ ] Storage paths use `{org_id}/{uuid}.{ext}` — no original filename in path
- [ ] `document_id` included as metadata in every vector — enables clean deletion

### Functionality
- [ ] 50-page PDF ingested, `status = "ready"`, chunks stored in ChromaDB within 60s
- [ ] `retrieve("pricing", org_A_id)` returns 0 results from org_B's documents
- [ ] Query with no matching context (score < 0.75) returns empty list (fallback triggered in Phase 6)
- [ ] `DELETE /documents/{id}` removes all vectors from ChromaDB and soft-deletes DB record
- [ ] Uploading 21 MB file returns `413 Payload Too Large`
- [ ] Unsupported file type returns `415 Unsupported Media Type`
- [ ] Corrupted PDF sets `status = "failed"` and stores `error_message`

### Performance
- [ ] 10-page PDF ingested in < 30 seconds on local machine
- [ ] Vector search returns top-5 results in < 150ms

### Testing
- [ ] `pytest backend/tests/test_rag.py -v` — all tests pass
- [ ] Test fixtures include: `sample.pdf`, `sample.docx`, `sample.txt`
- [ ] Test coverage for `rag/` module ≥ 80%
- [ ] Cross-tenant isolation test explicitly present

### What is NOT Acceptable
- Calling `chromadb` directly in routes or services (must go through `VectorStore` interface)
- Ingestion blocking the request thread (sync processing inside the route handler)
- Missing org_id metadata on stored vectors
- No test for the case where the document fails to parse
