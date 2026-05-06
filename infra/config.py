"""全局配置 — 环境变量驱动"""
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
    """Env vars passed from the control plane into each sandbox (Docker / documented for K8s secret keys)."""
    return {k: os.environ[k] for k in SANDBOX_ENV_KEYS if os.environ.get(k)}


class Config:
    # K8s
    K8S_NAMESPACE: str = os.getenv("K8S_NAMESPACE", "hermes-runtime")
    KUBECONFIG: str = os.getenv("KUBECONFIG", "")
    SANDBOX_IMAGE: str = os.getenv("SANDBOX_IMAGE", "hermes-runtime:latest")
    SANDBOX_PORT: int = int(os.getenv("SANDBOX_PORT", "8000"))
    SANDBOX_ENV_SECRET: str = os.getenv("SANDBOX_ENV_SECRET", "llm-secret")
    # Docker only: bind-mount host Hermes dir (~/.hermes) into the sandbox container
    SANDBOX_MOUNT_HERMES_CONFIG: bool = (
        os.getenv("SANDBOX_MOUNT_HERMES_CONFIG", "").lower() in ("1", "true", "yes")
    )
    HERMES_CONFIG_HOST_PATH: str = os.getenv(
        "HERMES_CONFIG_HOST_PATH",
        os.path.expanduser("~/.hermes"),
    )

    # 池
    POOL_WARM_SIZE: int = int(os.getenv("POOL_WARM_SIZE", "2"))
    POOL_MAX_SIZE: int = int(os.getenv("POOL_MAX_SIZE", "10"))
    SESSION_TIMEOUT: int = int(os.getenv("SESSION_TIMEOUT", "1800"))

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # LLM
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")


config = Config()
