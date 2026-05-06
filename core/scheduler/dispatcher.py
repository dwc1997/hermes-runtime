"""Dispatcher — FastAPI entry; Hermes runs in this process (OpenClaw-style split: brain on host)."""
from runtime.agent.agent_factory import HermesRuntimeBridge, create_agent
from core.session.session_router import SessionRouter


class Dispatcher:
    def __init__(self):
        self.hermes: HermesRuntimeBridge = create_agent()
        self.session_router = SessionRouter(self.hermes)

    async def dispatch(self, session_id: str, request: dict) -> dict:
        return await self.session_router.handle(session_id, request)

    async def destroy_session(self, session_id: str):
        await self.session_router.destroy_session(session_id)

    def status(self) -> dict:
        return {
            "execution_mode": "host_hermes",
            "description": (
                "Single in-process Hermes AIAgent per request turn; "
                "terminal/tool sandboxing uses Hermes terminal.backend "
                "(e.g. docker on the host — see Hermes Docker backend docs)."
            ),
        }
