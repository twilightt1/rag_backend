"""BM25 in-memory retriever — per conversation."""
import logging
import numpy as np
from rank_bm25 import BM25Okapi

log = logging.getLogger(__name__)


class BM25Retriever:
    def __init__(self):
        self._indexes: dict[str, tuple[BM25Okapi, list[dict]]] = {}

    def rebuild_sync(self, db, conversation_id: str) -> None:
        from sqlalchemy import select
        from app.models.document_chunk import DocumentChunk
        from app.models.document import Document

        rows = db.execute(
            select(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(Document.conversation_id == conversation_id, Document.status == "ready")
            .order_by(DocumentChunk.created_at)
        ).scalars().all()

        if not rows:
            self._indexes.pop(conversation_id, None)
            return
        chunk_dicts = [{"id": str(c.id), "content": c.content, "metadata": c.chunk_metadata} for c in rows]
        self._indexes[conversation_id] = (
            BM25Okapi([c["content"].lower().split() for c in chunk_dicts]),
            chunk_dicts,
        )
        log.info("BM25 rebuilt", extra={"conversation_id": conversation_id, "n": len(chunk_dicts)})

    async def rebuild_async(self, db, conversation_id: str) -> None:
        from sqlalchemy import select
        from app.models.document_chunk import DocumentChunk
        from app.models.document import Document

        result = await db.execute(
            select(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(Document.conversation_id == conversation_id, Document.status == "ready")
            .order_by(DocumentChunk.created_at)
        )
        rows = result.scalars().all()
        if not rows:
            self._indexes.pop(conversation_id, None)
            return
        chunk_dicts = [{"id": str(c.id), "content": c.content, "metadata": c.chunk_metadata} for c in rows]
        self._indexes[conversation_id] = (
            BM25Okapi([c["content"].lower().split() for c in chunk_dicts]),
            chunk_dicts,
        )

    async def search(self, query: str, top_k: int, conversation_id: str) -> list[dict]:
        loaded = self._indexes.get(conversation_id)
        if not loaded:
            return []
        index, chunks = loaded
        scores = index.get_scores(query.lower().split())
        top_n  = np.argsort(scores)[::-1][:top_k]
        return [
            {"content": chunks[i]["content"], "score": float(scores[i]),
             "source": "bm25", "rank": rank, "metadata": chunks[i]["metadata"]}
            for rank, i in enumerate(top_n) if scores[i] > 0
        ]

    def invalidate(self, conversation_id: str) -> None:
        self._indexes.pop(conversation_id, None)


bm25_retriever = BM25Retriever()
