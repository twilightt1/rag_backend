"""
Document ingestion pipeline — sync Celery task.

Changes vs. original:
  - Uses build_parent_child_chunks() from smart chunker
  - Inserts PARENT chunks into document_chunks (DB) — returned to LLM
  - Inserts CHILD chunks into document_chunks with parent_id metadata
  - Embeds only CHILD chunks into ChromaDB
  - Caches PARENT chunks in Redis via parent_store
  - BM25 index built on PARENT content (better semantic units)
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
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.config import settings

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine   = create_engine(sync_url, pool_pre_ping=True)

    with Session(engine) as db:
        try:
            _ingest(db, document_id)
        except Exception as exc:
            db.rollback()  # Rollback any flushed chunks before retrying or failing
            from celery.exceptions import Retry
            try:
                raise self.retry(exc=exc)
            except Retry:
                log.warning("Ingestion failed, retrying...", extra={"doc_id": document_id, "error": str(exc)})
                raise
            except Exception as final_exc:
                _fail(db, document_id, str(final_exc))
                log.error("Ingestion failed permanently", extra={"doc_id": document_id, "error": str(final_exc)})
                raise


def _ingest(db, document_id: str) -> None:
    import uuid as _uuid
    from app.models.document import Document
    from app.models.document_chunk import DocumentChunk
    from app import storage as minio
    from app.utils.chunker import extract_text, build_parent_child_chunks
    from app.retrieval.vector_retriever import upsert_chunks_sync
    from app.retrieval.bm25_retriever import bm25_retriever
    from app.retrieval.parent_store import store_parents_sync

    # 1. Load + mark processing
    doc = db.get(Document, document_id)
    if not doc:
        log.error("Document not found", extra={"doc_id": document_id})
        return

    conversation_id = str(doc.conversation_id)
    doc.status = "processing"
    db.commit()

    # 2. Download
    file_bytes = minio.get_object_sync(doc.file_path)

    # 3. Extract text
    text = extract_text(file_bytes, doc.mime_type)
    if not text.strip():
        raise ValueError("Could not extract text content from file.")

    # 4. Smart parent-child chunking
    parents, children = build_parent_child_chunks(
        text=text,
        document_id=document_id,
        conversation_id=conversation_id,
        filename=doc.filename,
    )
    if not children:
        raise ValueError("No chunks produced from document.")

    # 5. INSERT parent chunks into DB (chunk_type = "parent")
    for p in parents:
        db.add(DocumentChunk(
            id=p.id,
            document_id=document_id,
            content=p.content,
            chunk_index=p.index,
            metadata=p.metadata,
        ))
    db.flush()

    # 6. INSERT child chunks into DB (chunk_type = "child", references parent)
    for c in children:
        db.add(DocumentChunk(
            id=c.id,
            document_id=document_id,
            content=c.content,
            chunk_index=c.index,
            metadata=c.metadata,
        ))
    db.flush()

    # 7. Cache parents in Redis for fast lookup during retrieval
    store_parents_sync(
        conversation_id,
        [{"id": p.id, "content": p.content, "metadata": p.metadata} for p in parents],
    )

    # 8. Embed + upsert CHILD chunks into ChromaDB
    child_dicts = [
        {"id": c.id, "content": c.content, "metadata": c.metadata}
        for c in children
    ]
    upsert_chunks_sync(conversation_id, child_dicts)

    # 9. Build BM25 index on PARENT content (better semantic units for keyword search)
    parent_dicts = [
        {"id": p.id, "content": p.content, "metadata": p.metadata}
        for p in parents
    ]
    bm25_retriever.build_from_parents(conversation_id, parent_dicts)

    # 10. Mark ready
    doc.status      = "ready"
    doc.error_msg   = None
    doc.chunk_count = len(parents)   # report parent count to user
    db.commit()

    log.info(
        "Ingestion complete",
        extra={
            "doc_id":          document_id,
            "conversation_id": conversation_id,
            "parents":         len(parents),
            "children":        len(children),
        },
    )


def _fail(db, document_id: str, error: str) -> None:
    try:
        from app.models.document import Document
        doc = db.get(Document, document_id)
        if doc:
            doc.status    = "failed"
            doc.error_msg = error[:500]
            db.commit()
    except Exception:
        pass
