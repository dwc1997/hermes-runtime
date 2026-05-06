"""Agent Runtime 主入口"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import router
from infra.redis_client import close_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent-runtime")


@asynccontextmanager
async def lifespan(app):
    logger.info("Agent Runtime starting (host Hermes AIAgent + Redis session metadata)")
    yield
    logger.info("Agent Runtime shutting down")
    await close_redis()


app = FastAPI(
    title="Hermes Agent Runtime",
    description="OpenAI-compatible API; Hermes AIAgent in-process; tool sandbox via Hermes backends",
    lifespan=lifespan,
)
app.include_router(router)
