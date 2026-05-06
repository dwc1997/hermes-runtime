"""Session router — Redis metadata + in-process Hermes (single host runtime)."""
import logging
import time
from typing import Any, Dict, List

from infra.redis_client import session_delete, session_get, session_set
from runtime.agent.agent_factory import HermesRuntimeBridge

logger = logging.getLogger(__name__)


def _last_user_text(messages: List[Dict[str, Any]]) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") == "user":
            raw = msg.get("content", "")
            return raw if isinstance(raw, str) else str(raw)
    return ""


class SessionRouter:
    """Tracks session metadata in Redis; runs Nous Hermes AIAgent on the host process."""

    def __init__(self, hermes: HermesRuntimeBridge):
        self.hermes = hermes

    async def handle(self, session_id: str, request: dict) -> dict:
        state = await session_get(session_id) or {
            "session_id": session_id,
            "created_at": time.time(),
            "message_count": 0,
        }
        state["last_active"] = time.time()
        state["message_count"] = state.get("message_count", 0) + 1
        await session_set(session_id, state)

        user_text = _last_user_text(request.get("messages", []))
        content = await self.hermes.arun(
            user_text,
            session_id=session_id,
            model_override=request.get("model"),
        )
        return {"role": "assistant", "content": content}

    async def destroy_session(self, session_id: str):
        self.hermes.clear_session(session_id)
        await session_delete(session_id)
        logger.info("Session destroyed session_id=%s", session_id)
