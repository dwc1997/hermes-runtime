#!/usr/bin/env python3
"""
HTTP smoke: POST /v1/chat/completions with a prompt that should invoke sandbox_shell.

Run while uvicorn is up (B-line: SANDBOX_ROUTE_HERMES_TOOLS + SandboxManager).

  cd /path/to/agent-runtime && source .venv/bin/activate
  python scripts/verify_chat_sandbox_tool.py

Env:
  GATEWAY_URL       default http://127.0.0.1:8080
  VERIFY_MODEL      default mimo-v2.5-pro (use your provider model id)
  VERIFY_SESSION_ID default tool-verify-001
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    base = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8080").rstrip("/")
    model = os.environ.get("VERIFY_MODEL", "mimo-v2.5-pro")
    sid = os.environ.get("VERIFY_SESSION_ID", "tool-verify-001")

    body = {
        "session_id": sid,
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "You MUST call the sandbox_shell tool exactly once. "
                    "Use command: hostname && pwd && id\n"
                    "In your final reply, paste the complete sandbox_shell tool stdout only."
                ),
            }
        ],
    }

    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print(f"POST {base}/v1/chat/completions session_id={sid} model={model}\n", file=sys.stderr)

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(e.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Request failed: {e}", file=sys.stderr)
        print("Is uvicorn running on GATEWAY_URL?", file=sys.stderr)
        return 1

    try:
        data = json.loads(raw)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print(raw)
        return 1

    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    print("\n--- assistant content (compare hostname/pwd/id with host) ---", file=sys.stderr)
    print(content, file=sys.stderr)

    if "(no response)" in content or not content.strip():
        print("\nWARN: empty or no response — check Hermes logs and VERIFY_MODEL.", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
