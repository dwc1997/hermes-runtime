"""Sandbox Manager — 会话→Pod 映射 + 生命周期"""
import asyncio
import logging

from core.sandbox.sandbox_pool import SandboxPool
from infra.config import config

logger = logging.getLogger(__name__)


class SandboxManager:
    def __init__(self):
        self.pool = SandboxPool()

    async def acquire(self, session_id: str):
        return await self.pool.acquire(session_id)

    async def release(self, session_id: str) -> bool:
        return await self.pool.release(session_id)

    async def execute(self, session_id: str, request: dict) -> dict:
        """获取 Pod → HTTP 调用 /execute → 返回结果"""
        import httpx

        sb = await self.pool.acquire(session_id)

        # Docker: published host_port on localhost. K8s: cluster pod_ip + container port.
        if sb.host_port is not None:
            host = "127.0.0.1"
            port = sb.host_port
        else:
            host = sb.pod_ip
            port = sb.port

        # 等待 Pod 就绪 (K8s: pod_ip may be empty until scheduled)
        if not host:
            for _ in range(30):
                sb.pod_ip = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: __import__('core.sandbox.k8s_operator', fromlist=['get_pod_ip']).get_pod_ip(sb.sandbox_id)
                )
                if sb.pod_ip:
                    host = sb.pod_ip
                    break
                await asyncio.sleep(1)

        if not host:
            raise RuntimeError(f"Pod {sb.sandbox_id} has no IP after 30s")

        url = f"http://{host}:{port}/execute"

        # 等待 Pod 内 server 就绪
        async with httpx.AsyncClient(timeout=120) as c:
            for attempt in range(30):
                try:
                    resp = await c.post(url, json=request)
                    resp.raise_for_status()
                    return resp.json()
                except (httpx.ConnectError, httpx.ReadTimeout) as e:
                    if attempt < 29:
                        await asyncio.sleep(1)
                    else:
                        raise RuntimeError(f"Pod {sb.sandbox_id} not ready after 30s: {e}")

    def status(self) -> dict:
        return {
            "warm_available": self.pool.warm_count,
            "active_sessions": self.pool.active_count,
            "total_sandboxes": len(self.pool.sandboxes),
            "creating": self.pool._creating,
            "max_size": getattr(self.pool, "pool_max", config.POOL_MAX_SIZE),
        }
