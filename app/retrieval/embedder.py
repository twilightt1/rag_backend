import logging
from openai import AsyncOpenAI, OpenAI
from app.config import settings

log = logging.getLogger(__name__)

async_client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY
)

sync_client = OpenAI(
    api_key=settings.OPENAI_API_KEY
)

async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    try:
        response = await async_client.embeddings.create(
            model=settings.EMBED_MODEL,
            input=texts,
            timeout=30.0
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        log.error("Failed to get embeddings", exc_info=True)
        raise ValueError(f"Failed to get embeddings: {e}")


async def embed_query(query: str) -> list[float]:
    return (await embed_texts([query]))[0]


def embed_texts_sync(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    try:
        response = sync_client.embeddings.create(
            model=settings.EMBED_MODEL,
            input=texts,
            timeout=30.0
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        log.error("Failed to get embeddings (sync)", exc_info=True)
        raise ValueError(f"Failed to get embeddings: {e}")
