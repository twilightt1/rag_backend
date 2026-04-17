"""OpenAI embeddings client."""
import logging
from openai import AsyncOpenAI, OpenAI
from app.config import settings

log = logging.getLogger(__name__)

_async_client: AsyncOpenAI | None = None
_sync_client:  OpenAI | None      = None


def _get_async() -> AsyncOpenAI:
    global _async_client
    if _async_client is None:
        _async_client = AsyncOpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY
            )
    return _async_client


def _get_sync() -> OpenAI:
    global _sync_client
    if _sync_client is None:
        _sync_client = OpenAI(
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY
        )
    return _sync_client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = await _get_async().embeddings.create(
        model=settings.EMBED_MODEL,
        input=texts,
        dimensions=settings.EMBED_DIMENSIONS,
    )
    return [item.embedding for item in response.data]


async def embed_query(query: str) -> list[float]:
    return (await embed_texts([query]))[0]


def embed_texts_sync(texts: list[str]) -> list[list[float]]:
    """Sync version for Celery tasks."""
    if not texts:
        return []
    response = _get_sync().embeddings.create(
        model=settings.EMBED_MODEL,
        input=texts,
        dimensions=settings.EMBED_DIMENSIONS,
    )
    return [item.embedding for item in response.data]
