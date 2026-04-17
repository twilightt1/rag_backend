"""BM25 in-memory retriever — per conversation."""
import logging
import numpy as np
from collections import OrderedDict
from rank_bm25 import BM25Okapi

log = logging.getLogger(__name__)


class BM25Retriever:
    def __init__(self, max_size: int = 100):
        # LRU Cache: conversation_id -> (chunk_count, index, chunks)
        self._indexes: OrderedDict[str, tuple[int, BM25Okapi, list[dict]]] = OrderedDict()
        self.max_size = max_size

    async def _get_or_build_index(self, conversation_id: str) -> tuple[BM25Okapi, list[dict]] | None:
        from app.database import AsyncSessionLocal
        from sqlalchemy import select, func
        from app.models.document_chunk import DocumentChunk
        from app.models.document import Document

        async with AsyncSessionLocal() as db:
            # 1. Check current chunk count to detect new documents from Celery
            count_res = await db.execute(
                select(func.count(DocumentChunk.id))
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(Document.conversation_id == conversation_id, Document.status == "ready")
            )
            current_count = count_res.scalar() or 0

            if current_count == 0:
                self._indexes.pop(conversation_id, None)
                return None

            # 2. Check LRU Cache
            if conversation_id in self._indexes:
                cached_count, index, chunks = self._indexes[conversation_id]
                if cached_count == current_count:
                    self._indexes.move_to_end(conversation_id)
                    return index, chunks

            # 3. Cache Miss or Stale -> Rebuild
            result = await db.execute(
                select(DocumentChunk)
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(Document.conversation_id == conversation_id, Document.status == "ready")
                .order_by(DocumentChunk.created_at)
            )
            rows = result.scalars().all()

            if not rows:
                self._indexes.pop(conversation_id, None)
                return None

            chunk_dicts = [{"id": str(c.id), "content": c.content, "metadata": c.chunk_metadata} for c in rows]
            index = BM25Okapi([c["content"].lower().split() for c in chunk_dicts])

            # Store in LRU cache
            self._indexes[conversation_id] = (len(rows), index, chunk_dicts)
            self._indexes.move_to_end(conversation_id)

            # Evict if over capacity
            if len(self._indexes) > self.max_size:
                self._indexes.popitem(last=False)

            log.info("BM25 hydrated dynamically", extra={"conversation_id": conversation_id, "n": len(chunk_dicts)})
            return index, chunk_dicts

    def rebuild_sync(self, db, conversation_id: str) -> None:
        # No-op: indexes are built dynamically on search to prevent process desync
        pass

    async def rebuild_async(self, db, conversation_id: str) -> None:
        # No-op: indexes are built dynamically on search to prevent process desync
        pass

    async def search(self, query: str, top_k: int, conversation_id: str) -> list[dict]:
        loaded = await self._get_or_build_index(conversation_id)
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


bm25_retriever = BM25Retriever(max_size=100)
