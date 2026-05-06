"""API 路由 — OpenAI 兼容 + 管理端点"""
import time
import uuid
from fastapi import APIRouter
from core.scheduler.dispatcher import Dispatcher
from models.request import ChatRequest

router = APIRouter()
dispatcher = Dispatcher()


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    """OpenAI 兼容端点"""
    session_id = req.session_id or f"sess-{uuid.uuid4().hex[:8]}"

    result = await dispatcher.dispatch(session_id, {
        "messages": [m.model_dump() for m in req.messages],
        "session_id": session_id,
        "model": req.model,
    })

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "model": req.model,
        "created": int(time.time()),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.get("content", str(result)),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "session_id": session_id,
    }


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/status")
async def status():
    return dispatcher.status()


@router.delete("/sessions/{session_id}")
async def destroy_session(session_id: str):
    await dispatcher.destroy_session(session_id)
    return {"destroyed": session_id}
