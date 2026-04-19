"""
Contextual compression — filter irrelevant sentences from retrieved chunks.

After retrieval + reranking, each chunk may contain sentences that don't
actually answer the query. This step removes those sentences, keeping only
the most relevant parts.

Two-level compression:
  1. Sentence-level filter  — remove sentences with low relevance score
  2. Length guard           — skip compression for very short chunks (< 150 chars)

Uses Jina Reranker to score individual sentences against the query.
Falls back to returning the original chunk if API fails.
"""
from __future__ import annotations
import logging
import re
import httpx
from app.config import settings

log = logging.getLogger(__name__)

JINA_URL    = "https://api.jina.ai/v1/rerank"
MIN_SCORE   = 0.1    # sentences below this score are dropped
MIN_LENGTH  = 150    # chunks shorter than this skip compression
MAX_SENTENCES_PER_CHUNK = 20


def _split_sentences(text: str) -> list[str]:
    """Simple sentence splitter — handles English and Vietnamese."""
    # Split on . ! ? followed by space or newline
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    # Also split on newlines (for bullet points / paragraphs)
    result = []
    for s in sents:
        parts = [p.strip() for p in s.split("\n") if p.strip()]
        result.extend(parts)
    return [s for s in result if len(s) > 20]


async def compress_chunk(query: str, chunk_content: str) -> str:
    """
    Remove irrelevant sentences from chunk_content.
    Returns compressed text (may be same as input if all relevant).
    """
    if len(chunk_content) < MIN_LENGTH:
        return chunk_content

    sentences = _split_sentences(chunk_content)
    if len(sentences) <= 2:
        return chunk_content

    # Limit to avoid huge API calls
    sentences = sentences[:MAX_SENTENCES_PER_CHUNK]

    try:
        scores = await _score_sentences(query, sentences)
        kept   = [s for s, score in zip(sentences, scores) if score >= MIN_SCORE]

        if not kept:
            # If everything got filtered, keep top 2
            ranked = sorted(zip(sentences, scores), key=lambda x: x[1], reverse=True)
            kept   = [s for s, _ in ranked[:2]]

        compressed = " ".join(kept)
        # Only use compression if it's meaningfully shorter
        if len(compressed) < len(chunk_content) * 0.85:
            return compressed
        return chunk_content

    except Exception as e:
        log.warning("Compression failed, using original", extra={"error": str(e)})
        return chunk_content


async def compress_chunks(query: str, chunks: list[dict]) -> list[dict]:
    """
    Compress a list of chunk dicts in parallel.
    Each dict must have a "content" key. Returns new list with compressed content.
    """
    import asyncio

    async def _compress_one(chunk: dict) -> dict:
        compressed = await compress_chunk(query, chunk["content"])
        return {**chunk, "content": compressed, "compressed": True}

    return list(await asyncio.gather(*[_compress_one(c) for c in chunks]))


# ── Jina scoring ─────────────────────────────────────────────────────────────

async def _score_sentences(query: str, sentences: list[str]) -> list[float]:
    """Score each sentence against the query using Jina Reranker."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            JINA_URL,
            json={
                "model":     settings.JINA_RERANKER_MODEL,
                "query":     query,
                "documents": sentences,
                "top_n":     len(sentences),
            },
            headers={
                "Authorization": f"Bearer {settings.JINA_API_KEY}",
                "Content-Type":  "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    # Build score list aligned with input sentences
    scores = [0.0] * len(sentences)
    for item in data.get("results", []):
        idx = item.get("index", -1)
        if 0 <= idx < len(sentences):
            scores[idx] = item.get("relevance_score", 0.0)
    return scores
