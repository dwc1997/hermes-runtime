"""Pod FastAPI — forwards requests to Nous Hermes AIAgent."""
import logging

from fastapi import FastAPI

from runtime.agent.agent_factory import create_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("runtime")

app = FastAPI(title="Hermes Runtime Pod")
agent = None


@app.on_event("startup")
async def startup():
    global agent
    agent = create_agent()
    logger.info("Hermes AIAgent bridge initialized")


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "agent": agent is not None}


@app.post("/execute")
async def execute(req: dict):
    """Control plane calls this endpoint."""
    messages = req.get("messages", [])
    session_id = req.get("session_id") or "default"

    user_input = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            raw = msg.get("content", "")
            user_input = raw if isinstance(raw, str) else str(raw)
            break

    result = await agent.arun(user_input, session_id=session_id)

    return {
        "role": "assistant",
        "content": result,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
