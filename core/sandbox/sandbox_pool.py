"""容器池 — Warm/Active/Recycling 三态管理"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from core.sandbox.k8s_operator import create_sandbox_pod, delete_sandbox_pod, get_pod_ip
from infra.config import config
from infra.redis_client import sandbox_register, sandbox_unregister

logger = logging.getLogger(__name__)


@dataclass
class ManagedSandbox:
    sandbox_id: str      # Pod/Container 名
    pod_ip: Optional[str] = None
    host_port: Optional[int] = None  # Docker published port; None => K8s uses pod_ip + port
    state: str = "warm"  # warm | active | recycling
    session_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    port: int = 8000     # 容器内端口


class SandboxPool:
    def __init__(self):
        self.sandboxes: dict[str, ManagedSandbox] = {}
        self.warm_queue: list[str] = []
        self.session_map: dict[str, str] = {}  # session_id → sandbox_id
        self._lock = asyncio.Lock()
        self._creating = 0

    @property
    def warm_count(self) -> int:
        return len(self.warm_queue)

    @property
    def active_count(self) -> int:
        return len(self.session_map)

    async def acquire(self, session_id: str) -> ManagedSandbox:
        """获取容器：优先复用已有 → 预热池取 → 现场创建"""
        async with self._lock:
            # 1. 已有绑定
            if session_id in self.session_map:
                sid = self.session_map[session_id]
                sb = self.sandboxes.get(sid)
                if sb:
                    sb.last_active = time.time()
                    return sb

        # 2. 预热池
        async with self._lock:
            if self.warm_queue:
                warm_id = self.warm_queue.pop(0)
                sb = self.sandboxes.get(warm_id)
                if sb:
                    sb.state = "active"
                    sb.session_id = session_id
                    sb.last_active = time.time()
                    self.session_map[session_id] = warm_id
                    logger.info(f"🎯 分配预热 Pod {warm_id} → 会话 {session_id}")
                    return sb

        # 3. 现场创建
        if len(self.sandboxes) + self._creating >= config.POOL_MAX_SIZE:
            raise RuntimeError(f"Pool full ({len(self.sandboxes)}/{config.POOL_MAX_SIZE})")

        async with self._lock:
            self._creating += 1
        try:
            result = await asyncio.get_event_loop().run_in_executor(None, create_sandbox_pod)
            pod_name, pod_ip, host_port = result
            sb = ManagedSandbox(sandbox_id=pod_name, pod_ip=pod_ip, host_port=host_port,
                                state="active", session_id=session_id)
            async with self._lock:
                self.sandboxes[pod_name] = sb
                self.session_map[session_id] = pod_name
                self._creating -= 1
            await sandbox_register(pod_name, {
                "pod_ip": pod_ip, "host_port": host_port, "state": "active", "session_id": session_id
            })
            logger.info(f"🆕 现场创建 Pod {pod_name[:12]} → 会话 {session_id}")
            return sb
        except Exception:
            async with self._lock:
                self._creating -= 1
            raise

    async def release(self, session_id: str) -> bool:
        """释放会话 → 销毁 Pod"""
        async with self._lock:
            sid = self.session_map.pop(session_id, None)
            if not sid:
                return False
            sb = self.sandboxes.pop(sid, None)
            if not sb:
                return False

        await asyncio.get_event_loop().run_in_executor(
            None, lambda: delete_sandbox_pod(sid)
        )
        await sandbox_unregister(sid)
        logger.info(f"♻️  销毁 Pod {sid} (会话 {session_id})")
        return True

    async def refill_warm(self):
        """补充预热池"""
        async with self._lock:
            need = config.POOL_WARM_SIZE - len(self.warm_queue) - self._creating
            slots = config.POOL_MAX_SIZE - len(self.sandboxes) - self._creating
            need = min(need, slots)
        if need <= 0:
            return

        for _ in range(need):
            async with self._lock:
                self._creating += 1
            try:
                result = await asyncio.get_event_loop().run_in_executor(None, create_sandbox_pod)
                pod_name, pod_ip, host_port = result
                sb = ManagedSandbox(sandbox_id=pod_name, pod_ip=pod_ip, host_port=host_port, state="warm")
                async with self._lock:
                    self.sandboxes[pod_name] = sb
                    self.warm_queue.append(pod_name)
                    self._creating -= 1
                await sandbox_register(pod_name, {
                    "pod_ip": pod_ip, "host_port": host_port, "state": "warm"
                })
                logger.info(f"🔥 预热完成: {pod_name[:12]}")
            except Exception as e:
                async with self._lock:
                    self._creating -= 1
                logger.error(f"预热失败: {e}")

    async def cleanup_expired(self):
        """清理超时会话"""
        now = time.time()
        expired = []
        async with self._lock:
            for sid, cid in list(self.session_map.items()):
                sb = self.sandboxes.get(cid)
                if sb and (now - sb.last_active) > config.SESSION_TIMEOUT:
                    expired.append(sid)
        for sid in expired:
            await self.release(sid)
