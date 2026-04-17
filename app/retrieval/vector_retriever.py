"""ChromaDB vector retriever — collection per conversation: rag_conv_{id}"""
import logging
import chromadb
from app.config import settings
from app.retrieval.embedder import embed_texts, embed_query, embed_texts_sync

log = logging.getLogger(__name__)
_async_client = None


async def _get_async_client() -> chromadb.AsyncHttpClient:
    global _async_client
    if _async_client is None:
        _async_client = await chromadb.AsyncHttpClient(
            host=settings.CHROMA_HOST, port=settings.CHROMA_PORT
        )
    return _async_client


def _col(conversation_id: str) -> str:
    return f"rag_conv_{conversation_id}"


async def upsert_chunks(conversation_id: str, chunks: list[dict]) -> None:
    if not chunks:
        return
    client     = await _get_async_client()
    collection = await client.get_or_create_collection(
        _col(conversation_id), metadata={"hnsw:space": "cosine"}
    )
    embeddings = await embed_texts([c["content"] for c in chunks])
    await collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["content"] for c in chunks],
        embeddings=embeddings,
        metadatas=[c["metadata"] for c in chunks],
    )


async def search(query: str, top_k: int, conversation_id: str) -> list[dict]:
    try:
        client     = await _get_async_client()
        collection = await client.get_collection(_col(conversation_id))
    except Exception as e:
        log.warning("Failed to get collection for search", extra={"conversation_id": conversation_id, "error": str(e)})
        return []
    count = await collection.count()
    if count == 0:
        return []
    emb     = await embed_query(query)
    results = await collection.query(
        query_embeddings=[emb], n_results=min(top_k, count)
    )
    if not results["documents"] or not results["documents"][0]:
        return []
    return [
        {"content": doc, "score": 1 - dist, "source": "vector",
         "rank": i, "metadata": meta}
        for i, (doc, dist, meta) in enumerate(zip(
            results["documents"][0], results["distances"][0], results["metadatas"][0]
        ))
    ]


async def delete_document_chunks(conversation_id: str, document_id: str) -> None:
    try:
        client     = await _get_async_client()
        collection = await client.get_collection(_col(conversation_id))
        results    = await collection.get(where={"document_id": {"$eq": document_id}})
        if results["ids"]:
            await collection.delete(ids=results["ids"])
    except Exception as e:
        log.warning("Failed to delete chunks", extra={"error": str(e)})


async def delete_conversation_collection(conversation_id: str) -> None:
    try:
        client = await _get_async_client()
        await client.delete_collection(_col(conversation_id))
    except Exception as e:
        log.warning("Failed to delete conversation collection", extra={"conversation_id": conversation_id, "error": str(e)})


def upsert_chunks_sync(conversation_id: str, chunks: list[dict]) -> None:
    """Sync for Celery."""
    if not chunks:
        return

    try:
        client = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
        collection = client.get_or_create_collection(
            name=_col(conversation_id), metadata={"hnsw:space": "cosine"}
        )
        embeddings = embed_texts_sync([c["content"] for c in chunks])
        collection.upsert(
            ids=[c["id"] for c in chunks],
            documents=[c["content"] for c in chunks],
            embeddings=embeddings,
            metadatas=[c["metadata"] for c in chunks],
        )
        log.info("ChromaDB upsert complete", extra={"conversation_id": conversation_id, "n": len(chunks)})
    except Exception as e:
        log.error("Failed to connect to ChromaDB during ingestion", extra={"error": str(e)})
        # Instead of failing the entire Celery task, we let it pass.
        # Hybrid retrieval will naturally fallback to BM25 if the vector collection doesn't exist.
        pass
