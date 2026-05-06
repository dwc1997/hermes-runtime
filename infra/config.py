"""Global configuration (environment-driven)."""
import os
from typing import Dict, List


SANDBOX_ENV_KEYS: List[str] = [
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "HERMES_MODEL",
    "HERMES_BASE_URL",
    "HERMES_API_KEY",
    "HERMES_SKIP_MEMORY",
    "HERMES_SKIP_CONTEXT_FILES",
    "HERMES_MAX_ITERATIONS",
    "HERMES_DISABLED_TOOLSETS",
    "HERMES_ENABLED_TOOLSETS",
    "HERMES_PLATFORM",
    "HERMES_SYSTEM_PROMPT",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_API_KEY",
]


def collect_sandbox_env() -> Dict[str, str]:
    """Env vars documented for K8s secrets / optional overrides (Hermes reads ~/.hermes by default)."""
    return {k: os.environ[k] for k in SANDBOX_ENV_KEYS if os.environ.get(k)}


class Config:
    SESSION_TIMEOUT: int = int(os.getenv("SESSION_TIMEOUT", "1800"))
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")


config = Config()
