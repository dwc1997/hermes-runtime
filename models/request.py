"""请求模型 — OpenAI 兼容"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    session_id: Optional[str] = None
    model: str = "hermes"
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    model: str = "hermes"
    choices: List[Dict[str, Any]]
