"""沙箱模型"""
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class SandboxState(str, Enum):
    WARM = "warm"           # 预热池中
    ACTIVE = "active"       # 已绑定会话
    RECYCLING = "recycling"  # 销毁中


class SandboxInfo(BaseModel):
    sandbox_id: str         # Pod 名
    pod_ip: Optional[str] = None
    state: SandboxState = SandboxState.WARM
    session_id: Optional[str] = None
    port: int = 8000
