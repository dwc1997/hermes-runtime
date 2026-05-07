"""Blocking Redis client for Hermes tool handlers (sync thread context)."""
import redis

from infra.config import config

_client: redis.Redis | None = None


def sync_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    return _client
