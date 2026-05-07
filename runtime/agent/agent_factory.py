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
    Optional: bind each session_id to an AgentScope sandbox (SANDBOX_BIND_SESSION)
    and route shell/Python off the host via sandbox_shell / sandbox_python
    (SANDBOX_ROUTE_HERMES_TOOLS), disabling Hermes built-in terminal and code_execution.
    """

    _gateway_tools_registered = False
    # Hermes toolsets that run on the API host; replaced by gateway_sandbox when routing.
    _ROUTED_HOST_TOOLSETS = ("terminal", "code_execution")

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
        self._sandbox_container_by_session: Dict[str, str] = {}
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

    def get_sandbox_container(self, session_id: str) -> Optional[str]:
        return self._sandbox_container_by_session.get(session_id)

    def set_sandbox_container(self, session_id: str, container_name: str) -> None:
        self._sandbox_container_by_session[session_id] = container_name

    def clear_sandbox_container(self, session_id: str) -> None:
        self._sandbox_container_by_session.pop(session_id, None)

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
        self.clear_sandbox_container(session_id)
        with self._locks_guard:
            self._session_locks.pop(session_id, None)

    def _should_route_hermes_tools_to_sandbox(self) -> bool:
        try:
            from infra.agentscope_sandbox_service import get_agentscope_sandbox_manager
            from infra.runtime_sandbox_flags import sandbox_route_hermes_tools_enabled

            return (
                sandbox_route_hermes_tools_enabled()
                and get_agentscope_sandbox_manager() is not None
            )
        except Exception:
            return False

    @classmethod
    def _strip_routed_host_toolsets(cls, names: List[str]) -> List[str]:
        routed = set(cls._ROUTED_HOST_TOOLSETS)
        return [x for x in names if x not in routed]

    @staticmethod
    def _append_gateway_toolset(names: List[str], gateway_ts: str) -> List[str]:
        out = list(names)
        if gateway_ts not in out:
            out.append(gateway_ts)
        return out

    @classmethod
    def _disabled_with_routed_toolsets(cls, disabled: List[str]) -> List[str]:
        out = list(disabled)
        for ts in cls._ROUTED_HOST_TOOLSETS:
            if ts not in out:
                out.append(ts)
        return out

    def _ensure_gateway_tools(self) -> None:
        if HermesRuntimeBridge._gateway_tools_registered:
            return
        try:
            from runtime.hermes_gateway_sandbox_tools import (
                ensure_gateway_sandbox_tools_registered,
            )

            ensure_gateway_sandbox_tools_registered()
        except Exception as exc:
            logger.warning("Gateway sandbox Hermes tools not registered: %s", exc)
        HermesRuntimeBridge._gateway_tools_registered = True

    def _make_agent(self, *, model_override: Optional[str] = None):
        self._ensure_gateway_tools()

        kwargs: Dict[str, Any] = dict(
            quiet_mode=True,
            skip_memory=self._skip_memory,
            skip_context_files=self._skip_context_files,
            max_iterations=self._max_iterations,
        )
        resolved = self._resolve_model(model_override)
        if resolved:
            kwargs["model"] = resolved
        logger.info(
            "Hermes AIAgent build: model_kwarg=%r request_override=%r env_hermes_or_llm_model=%r",
            resolved,
            model_override,
            (self._model or None),
        )
        if self._ephemeral_system_prompt:
            kwargs["ephemeral_system_prompt"] = self._ephemeral_system_prompt
        if self._platform:
            kwargs["platform"] = self._platform

        gateway_ts = os.getenv("SANDBOX_GATEWAY_TOOLSET", "gateway_sandbox")
        route = self._should_route_hermes_tools_to_sandbox()

        if self._enabled:
            enabled = list(self._enabled)
            if route:
                enabled = self._append_gateway_toolset(
                    self._strip_routed_host_toolsets(enabled),
                    gateway_ts,
                )
            kwargs["enabled_toolsets"] = enabled
        elif self._disabled:
            disabled = list(self._disabled)
            if route:
                disabled = self._disabled_with_routed_toolsets(disabled)
            kwargs["disabled_toolsets"] = disabled
        else:
            if route:
                kwargs["disabled_toolsets"] = list(self._ROUTED_HOST_TOOLSETS)
            else:
                pass

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
            from runtime.hermes_active_context import set_active_hermes_bridge

            set_active_hermes_bridge(self)
            try:
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
                    logger.exception(
                        "Hermes run_conversation failed session_id=%s", session_id
                    )
                    return f"[Hermes Error] {e}"

                messages = result.get("messages")
                if messages is not None:
                    self._histories[session_id] = messages

                text = (result.get("final_response") or "").strip()
                if not text:
                    logger.warning(
                        "Hermes returned empty final_response session_id=%s",
                        session_id,
                    )
                    return "(no response)"
                return text
            finally:
                set_active_hermes_bridge(None)

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
