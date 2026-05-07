"""Bind chat session_id to one AgentScope sandbox container (acquire/release)."""
from __future__ import annotations

import logging
from typing import Any, Optional

from infra.config import config
from infra.redis_client import get_redis
from infra.runtime_sandbox_flags import sandbox_bind_session_enabled

logger = logging.getLogger(__name__)

BIND_KEY = "sandbox:bind:{session_id}"


def _bind_redis_key(session_id: str) -> str:
    return BIND_KEY.format(session_id=session_id)


async def ensure_session_sandbox(session_id: str, bridge: Any) -> None:
    if not sandbox_bind_session_enabled():
        return
    from core.sandbox_service.service import SandboxService

    if not SandboxService.enabled():
        return

    existing = bridge.get_sandbox_container(session_id)
    if existing:
        return

    r = await get_redis()
    key = _bind_redis_key(session_id)
    cached = await r.get(key)
    if cached:
        bridge.set_sandbox_container(session_id, cached)
        return

    try:
        data = await SandboxService.acquire(session_ctx_id=session_id)
        cn = data["container_name"]
    except Exception as exc:
        logger.warning(
            "Sandbox acquire failed session_id=%s (chat continues without sandbox): %s",
            session_id,
            exc,
        )
        return

    bridge.set_sandbox_container(session_id, cn)
    await r.set(key, cn, ex=config.SESSION_TIMEOUT)
    logger.info("Session sandbox bound session_id=%s container_name=%s", session_id, cn)


async def touch_sandbox_bind_ttl(session_id: str) -> None:
    if not sandbox_bind_session_enabled():
        return
    r = await get_redis()
    key = _bind_redis_key(session_id)
    if await r.exists(key):
        await r.expire(key, config.SESSION_TIMEOUT)


async def release_session_sandbox(session_id: str, bridge: Any) -> None:
    from core.sandbox_service.service import SandboxService

    r = await get_redis()
    key = _bind_redis_key(session_id)
    cn: Optional[str] = bridge.get_sandbox_container(session_id)
    if not cn:
        raw = await r.get(key)
        cn = raw if raw else None
    bridge.clear_sandbox_container(session_id)
    await r.delete(key)
    if not cn:
        return
    if not SandboxService.enabled():
        return
    try:
        await SandboxService.release(cn)
        logger.info("Session sandbox released session_id=%s container_name=%s", session_id, cn)
    except Exception as exc:
        logger.warning(
            "Sandbox release failed session_id=%s container_name=%s: %s",
            session_id,
            cn,
            exc,
        )
