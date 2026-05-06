"""会话模型 — 全部存 Redis，Pod 内无状态"""
from pydantic import BaseModel
from typing import Optional
import time


class SessionState(BaseModel):
    session_id: str
    sandbox_id: Optional[str] = None     # 绑定的 Pod 名
    sandbox_ip: Optional[str] = None     # Pod IP
    created_at: float = 0.0
    last_active: float = 0.0
    message_count: int = 0

    def touch(self):
        self.last_active = time.time()
        self.message_count += 1
