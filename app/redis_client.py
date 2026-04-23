from redis.asyncio import ConnectionPool, Redis
from app.config import settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_POOL_MAX,
            decode_responses=True,
        )
    return _pool


async def get_redis() -> Redis:
    return Redis(connection_pool=get_pool())
