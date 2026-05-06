"""内存管理 — Pod 内存对话历史（无状态，重启丢失）"""


class MemoryManager:
    """Pod 内临时记忆，不持久化"""

    def __init__(self, max_messages: int = 20):
        self.store: dict[str, list] = {}
        self.max_messages = max_messages

    def add(self, session_id: str, role: str, content: str):
        if session_id not in self.store:
            self.store[session_id] = []
        self.store[session_id].append({"role": role, "content": content})
        # 滚动截断
        if len(self.store[session_id]) > self.max_messages:
            self.store[session_id] = self.store[session_id][-self.max_messages:]

    def get(self, session_id: str) -> list:
        return self.store.get(session_id, [])

    def clear(self, session_id: str):
        self.store.pop(session_id, None)
