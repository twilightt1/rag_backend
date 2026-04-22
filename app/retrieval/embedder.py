"""OpenAI embeddings client."""
import logging
import httpx
from app.config import settings

log = logging.getLogger(__name__)

async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.FRONTEND_URL,
    }

    payload = {
        "model": settings.EMBED_MODEL,
        "input": texts,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.OPENROUTER_BASE_URL}/embeddings",
            headers=headers,
            json=payload,
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()
        if "data" not in data or not data["data"]:
            log.error("No embedding data received", extra={"response": data})
            raise ValueError("No embedding data received from API")

        return [item["embedding"] for item in data["data"]]


async def embed_query(query: str) -> list[float]:
    return (await embed_texts([query]))[0]


def embed_texts_sync(texts: list[str]) -> list[list[float]]:
    """Sync version for Celery tasks."""
    if not texts:
        return []

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.FRONTEND_URL,
    }

    payload = {
        "model": settings.EMBED_MODEL,
        "input": texts,
    }

    with httpx.Client() as client:
        response = client.post(
            f"{settings.OPENROUTER_BASE_URL}/embeddings",
            headers=headers,
            json=payload,
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()
        if "data" not in data or not data["data"]:
            log.error("No embedding data received", extra={"response": data})
            raise ValueError("No embedding data received from API")

        return [item["embedding"] for item in data["data"]]
