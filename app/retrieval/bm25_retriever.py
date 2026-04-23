from __future__ import annotations
import logging
import numpy as np
from rank_bm25 import BM25Okapi

log = logging.getLogger(__name__)


class BM25Retriever:
    def __init__(self):
                                                        
        self._indexes: dict[str, tuple[BM25Okapi, list[dict]]] = {}

                                                                                

    def build_from_parents(self, conversation_id: str, parents: list[dict]) -> None:
        if not parents:
            self._indexes.pop(conversation_id, None)
            return
        import re

        def tokenize(text: str) -> list[str]:
                                                                                       
            words = re.findall(r'\w+', text.lower())
            bigrams = [f"{words[i]}_{words[i+1]}" for i in range(len(words)-1)]
            return words + bigrams

        tokenized = [tokenize(p["content"]) for p in parents]
        self._indexes[conversation_id] = (BM25Okapi(tokenized), parents)
        log.info("BM25 built", extra={"conversation_id": conversation_id, "n": len(parents)})

    def rebuild_sync(self, db, conversation_id: str) -> None:
        from sqlalchemy import select
        from app.models.document_chunk import DocumentChunk
        from app.models.document import Document

        rows = db.execute(
            select(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(
                Document.conversation_id == conversation_id,
                Document.status == "ready",
                                    
                DocumentChunk.metadata["chunk_type"].astext == "parent",
            )
            .order_by(DocumentChunk.created_at)
        ).scalars().all()

        if not rows:
            self._indexes.pop(conversation_id, None)
            return

        parents = [{"id": str(c.id), "content": c.content, "metadata": c.metadata} for c in rows]
        self.build_from_parents(conversation_id, parents)

    async def rebuild_async(self, db, conversation_id: str) -> None:
        from sqlalchemy import select
        from app.models.document_chunk import DocumentChunk
        from app.models.document import Document

        result = await db.execute(
            select(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(
                Document.conversation_id == conversation_id,
                Document.status == "ready",
                DocumentChunk.metadata["chunk_type"].astext == "parent",
            )
            .order_by(DocumentChunk.created_at)
        )
        rows = result.scalars().all()

        if not rows:
            self._indexes.pop(conversation_id, None)
            return

        parents = [{"id": str(c.id), "content": c.content, "metadata": c.metadata} for c in rows]
        self.build_from_parents(conversation_id, parents)

                                                                                

    async def search(self, query: str, top_k: int, conversation_id: str) -> list[dict]:
        loaded = self._indexes.get(conversation_id)
        if not loaded:
            return []

        index, chunks = loaded
        import re
        words = re.findall(r'\w+', query.lower())
        bigrams = [f"{words[i]}_{words[i+1]}" for i in range(len(words)-1)]
        query_tokens = words + bigrams
        scores = index.get_scores(query_tokens)
        top_n  = np.argsort(scores)[::-1][:top_k]

        return [
            {
                "content":   chunks[i]["content"],
                "score":     float(scores[i]),
                "source":    "bm25",
                "rank":      rank,
                "metadata":  chunks[i]["metadata"],
                "parent_id": chunks[i]["id"],                                 
            }
            for rank, i in enumerate(top_n)
            if scores[i] > 0
        ]

    def invalidate(self, conversation_id: str) -> None:
        self._indexes.pop(conversation_id, None)


bm25_retriever = BM25Retriever()
