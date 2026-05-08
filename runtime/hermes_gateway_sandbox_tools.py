"""
Register Hermes tools that execute via AgentScope SandboxManager (route B).

Imports ``tools.registry`` from the installed ``hermes-agent`` package.
When SANDBOX_ROUTE_HERMES_TOOLS=1 and a manager is available, HermesRuntimeBridge
disables built-in ``terminal`` and ``code_execution`` toolsets and exposes
``sandbox_shell`` / ``sandbox_python`` instead (see HermesRuntimeBridge._make_agent).

Host-vs-Docker verification (no code edits required):
  Default: handlers call SandboxManager -> commands run inside the sandbox container.
  Set VERIFY_GATEWAY_TOOLS_ON_HOST=1 -> handlers run subprocess on the API host under
  VERIFY_GATEWAY_TOOLS_CWD (default: process cwd). Use the same Hermes prompt twice;
  then check whether the marker file exists on the host path vs only inside docker:
    docker exec -it <container_name> ls -la /workspace/hermes_verify_marker.txt
    ls -la "$VERIFY_GATEWAY_TOOLS_CWD/hermes_verify_marker.txt"
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Any, Dict

logger = logging.getLogger(__name__)

_GATEWAY_TOOLSET = os.getenv("SANDBOX_GATEWAY_TOOLSET", "gateway_sandbox")


def _tools_execute_on_host_for_verify() -> bool:
    """When true, skip Docker and run shell/Python on the uvicorn host (local verification only)."""
    return os.getenv("VERIFY_GATEWAY_TOOLS_ON_HOST", "").lower() in ("1", "true", "yes")


def _verify_host_cwd() -> str:
    return os.getenv("VERIFY_GATEWAY_TOOLS_CWD", os.getcwd())


def _verify_timeout_sec() -> int:
    try:
        return max(5, int(os.getenv("VERIFY_GATEWAY_TOOLS_TIMEOUT_SEC", "120")))
    except ValueError:
        return 120


def _run_shell_on_host(cmd: str) -> str:
    cwd = _verify_host_cwd()
    p = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_verify_timeout_sec(),
    )
    parts = [(p.stdout or ""), (p.stderr or "")]
    out = "".join(parts).rstrip()
    if p.returncode != 0:
        suffix = f"\n[exit {p.returncode}]"
        return (out + suffix) if out else suffix.strip()
    return out or "(no output)"


def _run_python_on_host(code: str) -> str:
    cwd = _verify_host_cwd()
    p = subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_verify_timeout_sec(),
    )
    parts = [(p.stdout or ""), (p.stderr or "")]
    out = "".join(parts).rstrip()
    if p.returncode != 0:
        suffix = f"\n[exit {p.returncode}]"
        return (out + suffix) if out else suffix.strip()
    return out or "(no output)"

_SHELL_SCHEMA = {
    "name": "sandbox_shell",
    "description": (
        "Run a non-interactive shell command inside the per-session isolated sandbox "
        "(Docker/K8s via AgentScope). Does not execute on the API host. "
        "Use for ls, grep, builds, scripts. No PTY; keep commands finite."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to run inside the session sandbox.",
            },
        },
        "required": ["command"],
    },
}

_PYTHON_SCHEMA = {
    "name": "sandbox_python",
    "description": (
        "Run Python code in an IPython cell inside the per-session sandbox "
        "(AgentScope run_ipython_cell)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source to execute.",
            },
        },
        "required": ["code"],
    },
}


def _check_gateway_sandbox_available() -> bool:
    if os.getenv("SANDBOX_ROUTE_HERMES_TOOLS", "1").lower() in ("0", "false", "no"):
        return False
    if _tools_execute_on_host_for_verify():
        return True
    try:
        from infra.agentscope_sandbox_service import get_agentscope_sandbox_manager

        return get_agentscope_sandbox_manager() is not None
    except Exception:
        return False


def _resolve_container(task_id: str | None, session_id: str | None) -> str | None:
    sid = task_id or session_id or ""
    if not sid:
        return None
    try:
        from runtime.hermes_active_context import get_active_hermes_bridge

        bridge = get_active_hermes_bridge()
        if bridge:
            cn = bridge.get_sandbox_container(sid)
            if cn:
                return cn
    except Exception:
        pass
    try:
        from infra.redis_sync_client import sync_redis
        from infra.session_sandbox_bind import BIND_KEY

        raw = sync_redis().get(BIND_KEY.format(session_id=sid))
        return raw if raw else None
    except Exception:
        return None


def _dispatch_shell(args: Dict[str, Any], task_id: str | None = None, session_id: str | None = None, **_kw: Any) -> str:
    from tools.registry import tool_error, tool_result

    cmd = (args or {}).get("command") or ""
    if not isinstance(cmd, str) or not cmd.strip():
        return tool_error("command is required")

    # --- VERIFY: host execution (set VERIFY_GATEWAY_TOOLS_ON_HOST=1). Default: Docker below. ---
    if _tools_execute_on_host_for_verify():
        cwd = _verify_host_cwd()
        logger.warning(
            "VERIFY_GATEWAY_TOOLS_ON_HOST: sandbox_shell runs on API host cwd=%s",
            cwd,
        )
        try:
            out = _run_shell_on_host(cmd.strip())
            return tool_result(result=out)
        except subprocess.TimeoutExpired:
            return tool_error("sandbox_shell timed out (host verify mode)")
        except Exception as exc:
            logger.exception("sandbox_shell failed (host verify mode)")
            return tool_error(f"sandbox_shell failed: {exc}")

    # --- Default: execute inside AgentScope sandbox container (Docker / remote manager) ---
    mgr = None
    try:
        from infra.agentscope_sandbox_service import get_agentscope_sandbox_manager

        mgr = get_agentscope_sandbox_manager()
    except Exception:
        pass
    if mgr is None:
        return tool_error("Sandbox manager is not enabled")

    cn = _resolve_container(task_id, session_id)
    if not cn:
        return tool_error(
            "No sandbox container for this session yet. Send a chat message first "
            "so the gateway can acquire a sandbox (SANDBOX_BIND_SESSION).",
        )

    try:
        out = mgr.call_tool(cn, "run_shell_command", {"command": cmd.strip()})
        return tool_result(result=out)
    except Exception as exc:
        logger.exception("sandbox_shell failed")
        return tool_error(f"sandbox_shell failed: {exc}")


def _dispatch_python(args: Dict[str, Any], task_id: str | None = None, session_id: str | None = None, **_kw: Any) -> str:
    from tools.registry import tool_error, tool_result

    code = (args or {}).get("code") or ""
    if not isinstance(code, str) or not code.strip():
        return tool_error("code is required")

    # --- VERIFY: host execution (set VERIFY_GATEWAY_TOOLS_ON_HOST=1). Default: Docker below. ---
    if _tools_execute_on_host_for_verify():
        cwd = _verify_host_cwd()
        logger.warning(
            "VERIFY_GATEWAY_TOOLS_ON_HOST: sandbox_python runs on API host cwd=%s",
            cwd,
        )
        try:
            out = _run_python_on_host(code.strip())
            return tool_result(result=out)
        except subprocess.TimeoutExpired:
            return tool_error("sandbox_python timed out (host verify mode)")
        except Exception as exc:
            logger.exception("sandbox_python failed (host verify mode)")
            return tool_error(f"sandbox_python failed: {exc}")

    # --- Default: execute inside AgentScope sandbox container ---
    mgr = None
    try:
        from infra.agentscope_sandbox_service import get_agentscope_sandbox_manager

        mgr = get_agentscope_sandbox_manager()
    except Exception:
        pass
    if mgr is None:
        return tool_error("Sandbox manager is not enabled")

    cn = _resolve_container(task_id, session_id)
    if not cn:
        return tool_error(
            "No sandbox container for this session yet. Send a chat message first.",
        )

    try:
        out = mgr.call_tool(cn, "run_ipython_cell", {"code": code})
        return tool_result(result=out)
    except Exception as exc:
        logger.exception("sandbox_python failed")
        return tool_error(f"sandbox_python failed: {exc}")


def ensure_gateway_sandbox_tools_registered() -> None:
    """Idempotent; safe to call multiple times."""
    try:
        from tools.registry import registry
    except ImportError as exc:
        logger.debug("hermes-agent tools.registry not importable yet: %s", exc)
        return

    if registry.get_entry("sandbox_shell"):
        return

    registry.register(
        name="sandbox_shell",
        toolset=_GATEWAY_TOOLSET,
        schema=_SHELL_SCHEMA,
        handler=_dispatch_shell,
        check_fn=_check_gateway_sandbox_available,
        description=_SHELL_SCHEMA["description"],
        emoji="📦",
    )
    registry.register(
        name="sandbox_python",
        toolset=_GATEWAY_TOOLSET,
        schema=_PYTHON_SCHEMA,
        handler=_dispatch_python,
        check_fn=_check_gateway_sandbox_available,
        description=_PYTHON_SCHEMA["description"],
        emoji="🐍",
    )
    logger.info(
        "Registered Hermes gateway sandbox tools: sandbox_shell, sandbox_python "
        "(toolset=%s)",
        _GATEWAY_TOOLSET,
    )
