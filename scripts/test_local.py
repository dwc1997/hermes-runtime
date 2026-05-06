#!/usr/bin/env python3
"""Local smoke test — host Hermes path (no per-session sandbox pods)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    print("═" * 50)
    print("Local smoke (host Hermes)")
    print("═" * 50)

    print("\n[1] Redis")
    try:
        from infra.redis_client import get_redis

        r = await get_redis()
        await r.ping()
        print("    OK")
    except Exception as e:
        print(f"    FAIL: {e}")
        return

    print("\n[2] Dispatcher + Hermes bridge")
    try:
        from core.scheduler.dispatcher import Dispatcher

        d = Dispatcher()
        print(f"    status: {d.status()}")
    except Exception as e:
        print(f"    FAIL: {e}")
        return

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
