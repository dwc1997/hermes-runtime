"""Minimal SandboxService — binds Agent chat sessions to AgentScope sandboxes.

Decision layer (Hermes) stays in-process; tool execution should go through this
service + upstream SandboxManager (embedded pool or remote HTTP).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from infra.agentscope_sandbox_service import get_agentscope_sandbox_manager

logger = logging.getLogger(__name__)


class SandboxService:
    """Thin facade over ``agentscope_runtime`` SandboxManager."""

    @staticmethod
    def enabled() -> bool:
        return get_agentscope_sandbox_manager() is not None

    @staticmethod
    async def acquire(
        session_ctx_id: str,
        sandbox_type: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        mgr = get_agentscope_sandbox_manager()
        if mgr is None:
            raise RuntimeError(
                "Sandbox backend disabled. Set SANDBOX_MANAGER_BASE_URL (remote) "
                "or AGENTSCOPE_SANDBOX_POOL_SIZE>0 (embedded pool).",
            )
        merged = {"session_ctx_id": session_ctx_id}
        if meta:
            merged.update(meta)
        container_name = await mgr.create_from_pool_async(
            sandbox_type=sandbox_type,
            meta=merged,
        )
        logger.info(
            "Sandbox acquired session_ctx_id=%s container_name=%s",
            session_ctx_id,
            container_name,
        )
        return {
            "container_name": container_name,
            "session_ctx_id": session_ctx_id,
        }

    @staticmethod
    async def release(container_name: str) -> bool:
        mgr = get_agentscope_sandbox_manager()
        if mgr is None:
            raise RuntimeError("Sandbox backend disabled.")
        ok = await mgr.release_async(container_name)
        logger.info("Sandbox release container_name=%s ok=%s", container_name, ok)
        return bool(ok)

    @staticmethod
    async def call_tool(
        container_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Invoke a tool inside the sandbox HTTP runtime (AgentScope convention).

        Common built-ins: ``run_ipython_cell`` (args: ``code``), ``run_shell_command``
        (args: ``command``). See sandbox container ``/mcp/list_tools``.
        """
        mgr = get_agentscope_sandbox_manager()
        if mgr is None:
            raise RuntimeError("Sandbox backend disabled.")
        return await mgr.call_tool_async(
            identity=container_name,
            tool_name=tool_name,
            arguments=arguments or {},
        )

    @staticmethod
    async def run_python(container_name: str, code: str) -> Any:
        return await SandboxService.call_tool(
            container_name,
            "run_ipython_cell",
            {"code": code},
        )

    @staticmethod
    async def run_shell(container_name: str, command: str) -> Any:
        return await SandboxService.call_tool(
            container_name,
            "run_shell_command",
            {"command": command},
        )
