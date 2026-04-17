"""
Document ingestion pipeline — sync Celery task.
Uses sync SQLAlchemy + sync MinIO to avoid asyncio event loop conflicts.
"""
import logging
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.process_document",
    max_retries=3,
    default_retry_delay=30,
    queue="ingestion",
)
def process_document(self, document_id: str) -> None:
    """
    Steps:
    1. Fetch Document record
    2. Set status = processing
    3. Download file from MinIO (sync)
    4. Extract text (PDF / DOCX / TXT)
    5. Chunk text (500 chars, 50 overlap)
    6. INSERT DocumentChunk rows
    7. Embed + upsert into ChromaDB (rag_conv_{conversation_id})
    8. Rebuild BM25 index for conversation
    9. Set status = ready
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.config import settings

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine   = create_engine(sync_url, pool_pre_ping=True)

    with Session(engine) as db:
        try:
            _run_ingestion(db, document_id)
        except Exception as exc:
            _mark_failed(db, document_id, str(exc))
            log.error("Ingestion failed", extra={"doc_id": document_id, "error": str(exc)})
            raise self.retry(exc=exc)


def _run_ingestion(db, document_id: str) -> None:
    from app.models.document import Document
    from app.models.document_chunk import DocumentChunk
    from app import storage as minio
    from app.utils.chunker import extract_text, chunk_text
    from app.retrieval.vector_retriever import upsert_chunks_sync
    from app.retrieval.bm25_retriever import bm25_retriever

    # 1. Load document
    doc = db.get(Document, document_id)
    if not doc:
        log.error("Document not found", extra={"doc_id": document_id})
        return

    conversation_id = str(doc.conversation_id)

    # 2. Mark processing
    doc.status = "processing"
    db.commit()

    # 3. Download from MinIO (sync)
    file_bytes = minio.get_object_sync(doc.file_path)

    # 4. Extract text
    text = extract_text(file_bytes, doc.mime_type)
    if not text.strip():
        raise ValueError("Could not extract text content from file.")

    # 5. Chunk
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    if not chunks:
        raise ValueError("No chunks produced from document.")

    # 6. INSERT chunks
    chunk_records = []
    for i, content in enumerate(chunks):
        import uuid as _uuid
        chunk_id = str(_uuid.uuid4())
        c = DocumentChunk(
            id=chunk_id,
            document_id=document_id,
            content=content,
            chunk_index=i,
            metadata={
                "document_id":    document_id,
                "filename":       doc.filename,
                "chunk_index":    i,
                "conversation_id": conversation_id,
            },
        )
        db.add(c)
        chunk_records.append({"id": chunk_id, "content": content, "metadata": c.chunk_metadata})

    db.flush()  # get IDs without committing

    # 7. Embed + upsert ChromaDB
    upsert_chunks_sync(conversation_id, chunk_records)

    # 8. Rebuild BM25
    bm25_retriever.rebuild_sync(db, conversation_id)

    # 9. Mark ready
    doc.status      = "ready"
    doc.chunk_count = len(chunks)
    db.commit()

    log.info(
        "Ingestion complete",
        extra={"doc_id": document_id, "conversation_id": conversation_id, "chunks": len(chunks)},
    )


def _mark_failed(db, document_id: str, error: str) -> None:
    try:
        from app.models.document import Document
        doc = db.get(Document, document_id)
        if doc:
            doc.status    = "failed"
            doc.error_msg = error[:500]
            db.commit()
    except Exception:
        pass
