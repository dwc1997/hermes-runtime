"""Agent Runtime 主入口"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import router
from infra.agentscope_sandbox_service import (
    init_agentscope_sandbox_manager,
    shutdown_agentscope_sandbox_manager_async,
)
from infra.redis_client import close_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent-runtime")


@asynccontextmanager
async def lifespan(app):
    logger.info("Agent Runtime starting (host Hermes AIAgent + Redis session metadata)")
    init_agentscope_sandbox_manager()
    yield
    logger.info("Agent Runtime shutting down")
    await shutdown_agentscope_sandbox_manager_async()
    await close_redis()


app = FastAPI(
    title="Hermes Agent Runtime",
    description=(
        "OpenAI-compatible API; Hermes AIAgent in-process; optional AgentScope "
        "SandboxManager (embedded pool or remote) for tool execution plane."
    ),
    lifespan=lifespan,
)
app.include_router(router)
