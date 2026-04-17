"""Sliding window rate limiter via Redis sorted sets."""
import time
import logging
from fastapi import HTTPException
from app.redis_client import get_redis

log = logging.getLogger(__name__)


async def check_rate_limit(
    user_id: str,
    window_seconds: int = 60,
    limit: int = 60,
) -> None:
    redis = await get_redis()
    key   = f"ratelimit:{user_id}:{window_seconds}"
    now   = time.time()

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, now - window_seconds)
    pipe.zcard(key)
    pipe.zadd(key, {str(now): now})
    pipe.expire(key, window_seconds)
    _, count, _, _ = await pipe.execute()

    if count >= limit:
        log.warning("Rate limit exceeded", extra={"user_id": user_id})
        raise HTTPException(
            429,
            detail={
                "error":       "rate_limit_exceeded",
                "retry_after": window_seconds,
                "limit":       limit,
            },
        )
