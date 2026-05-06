"""Redis 客户端 — 所有状态存储"""
import json
import redis.asyncio as aioredis
from infra.config import config

_pool: aioredis.Redis = None


async def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    return _pool


async def close_redis():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def session_get(session_id: str) -> dict | None:
    r = await get_redis()
    data = await r.get(f"session:{session_id}")
    return json.loads(data) if data else None


async def session_set(session_id: str, state: dict, ttl: int = None):
    r = await get_redis()
    ttl = ttl or config.SESSION_TIMEOUT
    await r.set(f"session:{session_id}", json.dumps(state), ex=ttl)


async def session_delete(session_id: str):
    r = await get_redis()
    await r.delete(f"session:{session_id}")


async def sandbox_register(sandbox_id: str, info: dict):
    r = await get_redis()
    await r.hset("sandboxes", sandbox_id, json.dumps(info))


async def sandbox_unregister(sandbox_id: str):
    r = await get_redis()
    await r.hdel("sandboxes", sandbox_id)


async def sandbox_get_all() -> dict:
    r = await get_redis()
    raw = await r.hgetall("sandboxes")
    return {k: json.loads(v) for k, v in raw.items()}
