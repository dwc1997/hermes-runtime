"""Feature flags for session sandbox binding and Hermes tool routing."""
import os


def sandbox_bind_session_enabled() -> bool:
    return os.getenv("SANDBOX_BIND_SESSION", "1").lower() in ("1", "true", "yes")


def sandbox_route_hermes_tools_enabled() -> bool:
    return os.getenv("SANDBOX_ROUTE_HERMES_TOOLS", "1").lower() in ("1", "true", "yes")


def gateway_sandbox_toolset() -> str:
    return os.getenv("SANDBOX_GATEWAY_TOOLSET", "gateway_sandbox")
