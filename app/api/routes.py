"""API 路由 — OpenAI 兼容 + 管理端点"""
import time
import uuid
from fastapi import APIRouter, HTTPException
from core.scheduler.dispatcher import Dispatcher
from core.sandbox_service import SandboxService
from infra.agentscope_sandbox_service import agentscope_sandbox_status
from models.request import ChatRequest
from models.sandbox_contract import (
    SandboxAcquireRequest,
    SandboxAcquireResponse,
    SandboxReleaseRequest,
)

router = APIRouter()
sandbox_router = APIRouter(prefix="/sandbox/v1", tags=["sandbox"])
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


@sandbox_router.get("/status")
async def sandbox_plane_status():
    """Whether SandboxService can acquire/release."""
    return {
        "sandbox_service_enabled": SandboxService.enabled(),
        "agentscope_runtime": agentscope_sandbox_status(),
    }


@sandbox_router.post("/acquire", response_model=SandboxAcquireResponse)
async def sandbox_acquire(body: SandboxAcquireRequest):
    """Bind a logical session to a sandbox container (pool or remote manager)."""
    try:
        data = await SandboxService.acquire(
            session_ctx_id=body.session_ctx_id,
            sandbox_type=body.sandbox_type,
            meta=body.meta,
        )
        return SandboxAcquireResponse(**data)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@sandbox_router.post("/release")
async def sandbox_release(body: SandboxReleaseRequest):
    """Release a sandbox container back to the manager."""
    try:
        ok = await SandboxService.release(body.container_name)
        return {"released": body.container_name, "ok": ok}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

router.include_router(sandbox_router)
