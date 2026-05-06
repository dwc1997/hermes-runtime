"""AgentScope Runtime SandboxManager bootstrap (embedded pool or remote HTTP client).

Upstream: https://github.com/agentscope-ai/agentscope-runtime

Priority:
1. ``SANDBOX_MANAGER_BASE_URL`` → thin HTTP client to a remote manager service.
2. ``AGENTSCOPE_SANDBOX_POOL_SIZE`` > 0 → embedded manager + watcher (local/K8s/docker per AgentScope config).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_manager: Any = None
_connection_mode: Optional[str] = None  # "remote" | "embedded"


def init_agentscope_sandbox_manager() -> None:
    """Construct SandboxManager (remote client or embedded pool)."""
    global _manager, _connection_mode
    _manager = None
    _connection_mode = None

    base_url = os.getenv("SANDBOX_MANAGER_BASE_URL", "").strip()
    if base_url:
        try:
            from agentscope_runtime.sandbox.manager import SandboxManager
        except ImportError as exc:
            logger.warning("agentscope-runtime not installed (%s); remote sandbox disabled", exc)
            return

        token = os.getenv("SANDBOX_MANAGER_TOKEN", "").strip() or None
        _manager = SandboxManager(base_url=base_url, bearer_token=token)
        _connection_mode = "remote"
        logger.info("SandboxManager remote mode base_url=%s", base_url)
        return

    pool_size = int(os.getenv("AGENTSCOPE_SANDBOX_POOL_SIZE", "0"))
    if pool_size <= 0:
        logger.info(
            "SandboxManager disabled (set SANDBOX_MANAGER_BASE_URL or AGENTSCOPE_SANDBOX_POOL_SIZE>0)",
        )
        return

    try:
        from agentscope_runtime.sandbox.manager import SandboxManager
        from agentscope_runtime.sandbox.model import SandboxManagerEnvConfig
    except ImportError as exc:
        logger.warning(
            "agentscope-runtime is not installed (%s); embedded sandbox pool disabled",
            exc,
        )
        return

    deployment = os.getenv("CONTAINER_DEPLOYMENT", "docker")
    interval = int(os.getenv("AGENTSCOPE_SANDBOX_WATCHER_INTERVAL", "15"))
    mount_dir = os.getenv("AGENTSCOPE_SANDBOX_MOUNT_DIR", "sessions_mount_dir")

    cfg = SandboxManagerEnvConfig(
        pool_size=pool_size,
        container_deployment=deployment,
        redis_enabled=False,
        watcher_scan_interval=interval,
        default_mount_dir=mount_dir,
    )
    _manager = SandboxManager(config=cfg)
    _manager.start_watcher()
    _connection_mode = "embedded"
    logger.info(
        "SandboxManager embedded pool_size=%s deployment=%s watcher_interval=%ss",
        pool_size,
        deployment,
        interval,
    )


async def shutdown_agentscope_sandbox_manager_async() -> None:
    global _manager, _connection_mode
    if _manager is None:
        return

    if _connection_mode == "remote":
        httpx_client = getattr(_manager, "httpx_client", None)
        if httpx_client is not None:
            try:
                await httpx_client.aclose()
            except Exception as exc:
                logger.warning("httpx client close: %s", exc)
        http_session = getattr(_manager, "http_session", None)
        if http_session is not None:
            try:
                http_session.close()
            except Exception as exc:
                logger.warning("requests session close: %s", exc)
        _manager = None
        _connection_mode = None
        return

    try:
        _manager.stop_watcher()
        _manager.cleanup()
    except Exception as exc:
        logger.warning("SandboxManager shutdown error: %s", exc)
    finally:
        _manager = None
        _connection_mode = None


def get_agentscope_sandbox_manager() -> Optional[Any]:
    return _manager


def get_sandbox_connection_mode() -> Optional[str]:
    return _connection_mode


def agentscope_sandbox_status() -> Dict[str, Any]:
    mgr = _manager
    if mgr is None:
        return {"enabled": False, "connection_mode": None}

    base: Dict[str, Any] = {
        "enabled": True,
        "connection_mode": _connection_mode,
        "docs": "https://github.com/agentscope-ai/agentscope-runtime",
    }

    if _connection_mode == "remote":
        base["base_url"] = getattr(mgr, "base_url", None)
        return base

    pool_metrics: Dict[str, Any] = {}
    try:
        pool_metrics = mgr.scan_pool_once()
    except Exception as exc:
        pool_metrics = {"error": str(exc)}
    base.update(
        {
            "pool_size": getattr(mgr, "pool_size", None),
            "container_deployment": getattr(mgr.config, "container_deployment", None),
            "last_pool_scan": pool_metrics,
        },
    )
    return base
