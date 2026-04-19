"""
ChromaDB vector retriever — conversation-scoped, child-chunk indexed.

Collection: rag_conv_{conversation_id}
Only CHILD chunks are stored (small, 300 chars).
Parent content is resolved via parent_store after retrieval.

HyDE support: caller passes hyde_text instead of the raw query for embedding.
"""
from __future__ import annotations
import logging
import chromadb
from app.config import settings
from app.retrieval.embedder import embed_texts, embed_query, embed_texts_sync

log = logging.getLogger(__name__)
_async_client: chromadb.AsyncHttpClient | None = None


async def _client() -> chromadb.AsyncHttpClient:
    global _async_client
    if _async_client is None:
        _async_client = await chromadb.AsyncHttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
        )
    return _async_client


def _col_name(conversation_id: str) -> str:
    return f"rag_conv_{conversation_id}"


# ── Upsert (ingestion) ────────────────────────────────────────────────────────

async def upsert_chunks(conversation_id: str, chunks: list[dict]) -> None:
    """
    Upsert child chunks.
    chunks: [{ id, content, metadata }]
    """
    if not chunks:
        return
    cli        = await _client()
    collection = await cli.get_or_create_collection(
        _col_name(conversation_id),
        metadata={"hnsw:space": "cosine"},
    )
    embeddings = await embed_texts([c["content"] for c in chunks])
    await collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["content"] for c in chunks],
        embeddings=embeddings,
        metadatas=[c["metadata"] for c in chunks],
    )
    log.info("Upserted child chunks", extra={"conversation_id": conversation_id, "n": len(chunks)})


def upsert_chunks_sync(conversation_id: str, chunks: list[dict]) -> None:
    """Sync for Celery."""
    cli        = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
    collection = cli.get_or_create_collection(
        _col_name(conversation_id),
        metadata={"hnsw:space": "cosine"},
    )
    embeddings = embed_texts_sync([c["content"] for c in chunks])
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["content"] for c in chunks],
        embeddings=embeddings,
        metadatas=[c["metadata"] for c in chunks],
    )


# ── Search ────────────────────────────────────────────────────────────────────

async def search(
    query: str,
    top_k: int,
    conversation_id: str,
    hyde_text: str | None = None,
) -> list[dict]:
    """
    Search child chunks. If hyde_text is provided, embed that instead of query.
    Returns list of child chunk dicts with content + metadata.
    """
    try:
        cli        = await _client()
        collection = await cli.get_collection(_col_name(conversation_id))
    except Exception:
        return []

    count = await collection.count()
    if count == 0:
        return []

    # Embed hyde_text for retrieval, but keep original query in metadata
    embed_input = hyde_text if hyde_text else query
    embedding   = await embed_query(embed_input)

    results = await collection.query(
        query_embeddings=[embedding],
        n_results=min(top_k, count),
    )

    if not results["documents"] or not results["documents"][0]:
        return []

    return [
        {
            "content":   doc,
            "score":     1 - dist,
            "source":    "vector",
            "rank":      i,
            "metadata":  meta,
            "child_id":  meta.get("child_id", ""),
            "parent_id": meta.get("parent_id", ""),
        }
        for i, (doc, dist, meta) in enumerate(zip(
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0],
        ))
    ]


# ── Cleanup ───────────────────────────────────────────────────────────────────

async def delete_document_chunks(conversation_id: str, document_id: str) -> None:
    try:
        cli        = await _client()
        collection = await cli.get_collection(_col_name(conversation_id))
        results    = await collection.get(where={"document_id": {"$eq": document_id}})
        if results["ids"]:
            await collection.delete(ids=results["ids"])
    except Exception as e:
        log.warning("Failed to delete chunks", extra={"error": str(e)})


async def delete_conversation_collection(conversation_id: str) -> None:
    try:
        cli = await _client()
        await cli.delete_collection(_col_name(conversation_id))
    except Exception:
        pass
