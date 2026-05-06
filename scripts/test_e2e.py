#!/usr/bin/env python3
"""端到端测试 — 控制面 + 沙箱 + /v1/chat/completions"""
import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import httpx


async def test_e2e():
    print("═" * 50)
    print("🧪 端到端测试")
    print("═" * 50)

    BASE = "http://localhost:8000"

    # 1. 启动控制面
    print("\n🚀 1. 启动控制面...")
    import subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env={**os.environ},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    await asyncio.sleep(3)
    print(f"   控制面 PID: {proc.pid}")

    async with httpx.AsyncClient(timeout=120) as c:
        # 2. 健康检查
        print("\n📊 2. 健康检查...")
        try:
            r = await c.get(f"{BASE}/health")
            print(f"   ✅ {r.json()}")
        except Exception as e:
            print(f"   ❌ 控制面未启动: {e}")
            proc.terminate()
            return

        # 3. 状态
        print("\n📊 3. 初始状态...")
        r = await c.get(f"{BASE}/status")
        print(f"   {r.json()}")

        # 4. 发送聊天请求
        print("\n💬 4. 发送聊天请求...")
        t0 = time.time()
        try:
            r = await c.post(f"{BASE}/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "Hello Hermes!"}],
                "session_id": "test-e2e-1",
            })
            elapsed = time.time() - t0
            resp = r.json()
            print(f"   ✅ 响应 ({elapsed:.1f}s):")
            print(f"   {resp.get('choices', [{}])[0].get('message', {}).get('content', 'N/A')[:100]}")
            print(f"   session_id: {resp.get('session_id', 'N/A')}")
        except Exception as e:
            print(f"   ❌ 请求失败: {e}")

        # 5. 状态 (应有活跃会话)
        print("\n📊 5. 执行后状态...")
        r = await c.get(f"{BASE}/status")
        print(f"   {r.json()}")

        # 6. 销毁会话
        print("\n♻️  6. 销毁会话...")
        try:
            r = await c.delete(f"{BASE}/sessions/test-e2e-1")
            print(f"   ✅ {r.json()}")
        except Exception as e:
            print(f"   ❌ 销毁失败: {e}")

    # 清理
    proc.terminate()
    print("\n" + "═" * 50)
    print("✅ 端到端测试完成!")
    print("═" * 50)


if __name__ == "__main__":
    asyncio.run(test_e2e())
