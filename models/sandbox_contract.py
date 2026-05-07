"""Request/response models for SandboxService HTTP API."""
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SandboxAcquireRequest(BaseModel):
    session_ctx_id: str = Field(..., min_length=1)
    sandbox_type: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class SandboxAcquireResponse(BaseModel):
    container_name: str
    session_ctx_id: str


class SandboxReleaseRequest(BaseModel):
    container_name: str = Field(..., min_length=1)


class SandboxRunPythonRequest(BaseModel):
    container_name: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1)


class SandboxRunShellRequest(BaseModel):
    container_name: str = Field(..., min_length=1)
    command: str = Field(..., min_length=1)
