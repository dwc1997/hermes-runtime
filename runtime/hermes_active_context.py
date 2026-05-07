"""Process-local active Hermes bridge during ``run_conversation`` (tool handlers)."""

from __future__ import annotations

from typing import Any, Optional

_active: Optional[Any] = None


def set_active_hermes_bridge(bridge: Optional[Any]) -> None:
    global _active
    _active = bridge


def get_active_hermes_bridge() -> Optional[Any]:
    return _active
