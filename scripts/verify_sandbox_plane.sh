#!/usr/bin/env bash
# Minimal sandbox-plane smoke test (AgentScope SandboxManager).
#
# Prerequisites: Docker running; same venv/deps as verify_host_hermes.sh; pulls sandbox images on first use.
#
# Usage (after Redis + app are up, or run standalone — starts Redis if missing):
#   AGENTSCOPE_SANDBOX_POOL_SIZE=1 REDIS_URL=redis://127.0.0.1:16379/0 bash scripts/verify_sandbox_plane.sh
#
# Or chain after verify_host_hermes.sh stops the server: start uvicorn yourself with pool env, then:
#   BASE=http://127.0.0.1:8080 bash scripts/verify_sandbox_plane.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BASE="${BASE:-http://127.0.0.1:8080}"
VERIFY_REDIS_HOST_PORT="${VERIFY_REDIS_HOST_PORT:-16379}"

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
else
  PY="${VIRTUAL_ENV:-}/bin/python"
  if [[ ! -x "$PY" ]]; then
    PY="python3"
  fi
fi

need_pool="${AGENTSCOPE_SANDBOX_POOL_SIZE:-0}"
if [[ "$need_pool" -lt 1 ]] && [[ -z "${SANDBOX_MANAGER_BASE_URL:-}" ]]; then
  echo "Set AGENTSCOPE_SANDBOX_POOL_SIZE>=1 or SANDBOX_MANAGER_BASE_URL for this test."
  exit 1
fi

if ! curl -sf "${BASE}/health" >/dev/null 2>&1; then
  echo "Starting Redis + uvicorn (foreground Redis already from verify script recommended)"
  docker rm -f agent-runtime-redis-sbx 2>/dev/null || true
  docker run -d --name agent-runtime-redis-sbx \
    -p "${VERIFY_REDIS_HOST_PORT}:6379" redis:7-alpine >/dev/null
  export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:${VERIFY_REDIS_HOST_PORT}/0}"
  export AGENTSCOPE_SANDBOX_POOL_SIZE="${AGENTSCOPE_SANDBOX_POOL_SIZE:-1}"
  export CONTAINER_DEPLOYMENT="${CONTAINER_DEPLOYMENT:-docker}"
  "${PY}" -m uvicorn app.main:app --host 127.0.0.1 --port 8080 &
  UV_PID=$!
  trap 'kill "${UV_PID}" 2>/dev/null; docker rm -f agent-runtime-redis-sbx 2>/dev/null || true' EXIT
  for i in $(seq 1 45); do
    curl -sf "${BASE}/health" >/dev/null && break
    sleep 1
    if [[ "$i" -eq 45 ]]; then
      echo "ERROR: server not ready"
      exit 1
    fi
  done
fi

echo "=== GET ${BASE}/sandbox/v1/status ==="
curl -s "${BASE}/sandbox/v1/status" | "${PY}" -m json.tool || curl -s "${BASE}/sandbox/v1/status"
echo ""

echo "=== POST acquire (session_ctx_id=verify-smoke-1) ==="
RESP="$(curl -s -X POST "${BASE}/sandbox/v1/acquire" \
  -H "Content-Type: application/json" \
  -d '{"session_ctx_id":"verify-smoke-1","sandbox_type":"base"}')"
echo "$RESP" | "${PY}" -m json.tool || echo "$RESP"
CN="$(echo "$RESP" | "${PY}" -c "import sys,json; print(json.load(sys.stdin).get('container_name',''))" 2>/dev/null || true)"
if [[ -z "$CN" ]]; then
  echo "ERROR: acquire did not return container_name (is Docker available? pool warming may take time)."
  exit 1
fi

echo "=== POST release ($CN) ==="
curl -s -X POST "${BASE}/sandbox/v1/release" \
  -H "Content-Type: application/json" \
  -d "{\"container_name\":\"${CN}\"}" | "${PY}" -m json.tool || true
echo ""
echo "Done."
