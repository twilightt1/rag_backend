"""Jina Reranker API."""
import logging
import httpx
from app.config import settings

log = logging.getLogger(__name__)
JINA_URL = "https://api.jina.ai/v1/rerank"


async def rerank(query: str, chunks: list[dict]) -> list[dict]:
    """Rerank chunks via Jina API. Returns top-N sorted by relevance."""
    if not chunks:
        return []

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            JINA_URL,
            json={
                "model":     settings.JINA_RERANKER_MODEL,
                "query":     query,
                "documents": [c["content"] for c in chunks],
                "top_n":     settings.JINA_RERANKER_TOP_N,
            },
            headers={
                "Authorization": f"Bearer {settings.JINA_API_KEY}",
                "Content-Type":  "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    reranked = []
    for item in data.get("results", []):
        original = chunks[item["index"]].copy()
        original["rerank_score"] = item["relevance_score"]
        reranked.append(original)

    reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
    log.info("Reranked", extra={"in": len(chunks), "out": len(reranked)})
    return reranked

