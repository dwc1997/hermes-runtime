"""Bridge to Nous Hermes AIAgent — runs in the control-plane process (host)."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# OpenAI-compat placeholder — do not send to Hermes as a real model id
_DEFAULT_GATEWAY_MODEL_PLACEHOLDER = "hermes"


def _split_csv(env_val: str) -> Optional[List[str]]:
    if not env_val or not env_val.strip():
        return None
    out = [x.strip() for x in env_val.split(",") if x.strip()]
    return out or None


class HermesRuntimeBridge:
    """
    Hermes AIAgent on the host: one installation, in-process calls.

    Session isolation: conversation_history + task_id per session_id.
    Tool/exec isolation: configure Hermes ``terminal.backend: docker`` (or ssh/modal/...)
    so shells run outside this process — see Hermes docs:
    https://hermes-agent.nousresearch.com/docs/user-guide/docker
    """

    def __init__(self) -> None:
        try:
            from run_agent import AIAgent
        except ImportError as e:
            raise ImportError(
                "hermes-agent is not installed. pip install -r requirements.txt"
            ) from e

        self._AIAgent = AIAgent
        self._histories: Dict[str, List[Dict[str, Any]]] = {}
        self._session_locks: Dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._model = os.getenv("HERMES_MODEL") or os.getenv("LLM_MODEL") or ""
        self._disabled = _split_csv(os.getenv("HERMES_DISABLED_TOOLSETS", ""))
        self._enabled = _split_csv(os.getenv("HERMES_ENABLED_TOOLSETS", ""))
        self._max_iterations = int(os.getenv("HERMES_MAX_ITERATIONS", "90"))
        self._skip_memory = os.getenv("HERMES_SKIP_MEMORY", "true").lower() == "true"
        self._skip_context_files = (
            os.getenv("HERMES_SKIP_CONTEXT_FILES", "true").lower() == "true"
        )
        self._platform = os.getenv("HERMES_PLATFORM") or None
        _ep = os.getenv("HERMES_SYSTEM_PROMPT")
        self._ephemeral_system_prompt = _ep if _ep else None

    def _resolve_model(self, request_model: Optional[str]) -> Optional[str]:
        """Prefer explicit API model, then env; omit so Hermes loads ~/.hermes/config.yaml."""
        if request_model and request_model.strip():
            name = request_model.strip()
            if name.lower() != _DEFAULT_GATEWAY_MODEL_PLACEHOLDER.lower():
                return name
        if self._model:
            return self._model
        return None

    def _lock_for(self, session_id: str) -> threading.Lock:
        with self._locks_guard:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = threading.Lock()
            return self._session_locks[session_id]

    def clear_session(self, session_id: str) -> None:
        with self._locks_guard:
            lock = self._session_locks.get(session_id)
        if lock:
            with lock:
                self._histories.pop(session_id, None)
        else:
            self._histories.pop(session_id, None)
        with self._locks_guard:
            self._session_locks.pop(session_id, None)

    def _make_agent(self, *, model_override: Optional[str] = None):
        kwargs: Dict[str, Any] = dict(
            quiet_mode=True,
            skip_memory=self._skip_memory,
            skip_context_files=self._skip_context_files,
            max_iterations=self._max_iterations,
        )
        resolved = self._resolve_model(model_override)
        if resolved:
            kwargs["model"] = resolved
        if self._ephemeral_system_prompt:
            kwargs["ephemeral_system_prompt"] = self._ephemeral_system_prompt
        if self._platform:
            kwargs["platform"] = self._platform
        if self._enabled:
            kwargs["enabled_toolsets"] = self._enabled
        elif self._disabled:
            kwargs["disabled_toolsets"] = self._disabled

        # Optional overrides only. If unset, Hermes resolves keys/model like the CLI
        # from ~/.hermes/.env and ~/.hermes/config.yaml (same as `hermes` on the host).
        api_key = (
            os.getenv("HERMES_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
        )
        base_url = (
            os.getenv("HERMES_BASE_URL")
            or os.getenv("OPENROUTER_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or None
        )
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url

        return self._AIAgent(**kwargs)

    def run_turn(
        self,
        user_text: str,
        session_id: str,
        *,
        model_override: Optional[str] = None,
    ) -> str:
        if not user_text.strip():
            return ""

        lock = self._lock_for(session_id)
        with lock:
            agent = self._make_agent(model_override=model_override)
            history = self._histories.get(session_id)

            try:
                call_kw: Dict[str, Any] = dict(
                    user_message=user_text,
                    task_id=session_id,
                )
                if history:
                    call_kw["conversation_history"] = history
                result = agent.run_conversation(**call_kw)
            except Exception as e:
                logger.exception("Hermes run_conversation failed session_id=%s", session_id)
                return f"[Hermes Error] {e}"

            messages = result.get("messages")
            if messages is not None:
                self._histories[session_id] = messages

            text = (result.get("final_response") or "").strip()
            if not text:
                logger.warning("Hermes returned empty final_response session_id=%s", session_id)
                return "(no response)"
            return text

    async def arun(
        self,
        user_text: str,
        session_id: str,
        *,
        model_override: Optional[str] = None,
    ) -> str:
        return await asyncio.to_thread(
            self.run_turn,
            user_text,
            session_id,
            model_override=model_override,
        )


def create_agent() -> HermesRuntimeBridge:
    return HermesRuntimeBridge()
