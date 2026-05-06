#!/usr/bin/env bash
# Idempotent local verification: single Hermes on host + Redis session metadata.
# Requires: Docker (for Redis), Python 3.11+, network for pip/GitHub on first run.
#
# Usage:
#   bash scripts/verify_host_hermes.sh
#
# Optional: export OPENROUTER_API_KEY=... (or rely on ~/.hermes/.env like the CLI).
# Chat round-trip runs when OPENROUTER_API_KEY is set OR ~/.hermes/.env exists.
#
# Optional cleanup (NOT run automatically — destructive):
#   docker rmi hermes-runtime:latest agent-runtime:latest
#   kind delete cluster --name hermes-runtime
#
# Redis binds host port VERIFY_REDIS_HOST_PORT (default 16379) to avoid clashing
# with an existing Redis on 6379. Override: VERIFY_REDIS_HOST_PORT=6379 bash ...
#
# Python: uses ./.venv if present, else $VIRTUAL_ENV, else creates ./.venv via
# python3 -m venv (avoids Debian/Ubuntu PEP 668 "externally-managed-environment").
# Some distros ship venvs without pip — see bootstrap_pip below.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERIFY_REDIS_HOST_PORT="${VERIFY_REDIS_HOST_PORT:-16379}"

bootstrap_pip() {
  local py="$1"
  if "${py}" -m pip --version >/dev/null 2>&1; then
    return 0
  fi
  echo "      No pip in this interpreter; trying ensurepip..."
  if "${py}" -m ensurepip --upgrade 2>/dev/null && "${py}" -m pip --version >/dev/null 2>&1; then
    return 0
  fi
  echo "      ensurepip unavailable; installing pip via get-pip.py..."
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://bootstrap.pypa.io/get-pip.py | "${py}"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://bootstrap.pypa.io/get-pip.py | "${py}"
  else
    echo "      ERROR: cannot bootstrap pip (need curl or wget)."
    echo "      Or install OS packages: sudo apt install python3-pip python3-venv python3-full"
    exit 1
  fi
}

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
elif [[ -n "${VIRTUAL_ENV:-}" ]] && [[ -x "${VIRTUAL_ENV}/bin/python" ]]; then
  PY="${VIRTUAL_ENV}/bin/python"
else
  echo "[bootstrap] Creating ${ROOT}/.venv (system Python is externally managed)"
  if ! python3 -m venv --upgrade-deps "${ROOT}/.venv" 2>/dev/null; then
    python3 -m venv "${ROOT}/.venv"
  fi
  PY="${ROOT}/.venv/bin/python"
fi
echo "      Using Python: ${PY}"

echo "═══════════════════════════════════════════════════════════"
echo "  verify_host_hermes.sh — idempotent checks"
echo "═══════════════════════════════════════════════════════════"

echo ""
echo "[1/6] Remove legacy per-session sandbox containers (label managed-by=agent-runtime)"
if IDS="$(docker ps -aq --filter label=managed-by=agent-runtime 2>/dev/null)"; then
  if [[ -n "${IDS}" ]]; then
    docker rm -f ${IDS} || true
    echo "      Removed: ${IDS}"
  else
    echo "      None found."
  fi
else
  echo "      Docker not available — skip."
fi

echo ""
echo "[2/6] Redis container agent-runtime-redis (host port ${VERIFY_REDIS_HOST_PORT})"
docker rm -f agent-runtime-redis 2>/dev/null || true
if ! docker run -d --name agent-runtime-redis \
  -p "${VERIFY_REDIS_HOST_PORT}:6379" redis:7-alpine >/dev/null; then
  echo "      ERROR: docker run failed (port ${VERIFY_REDIS_HOST_PORT} in use?). Try:"
  echo "        VERIFY_REDIS_HOST_PORT=26379 bash scripts/verify_host_hermes.sh"
  exit 1
fi
echo "      Redis up on redis://127.0.0.1:${VERIFY_REDIS_HOST_PORT}/0"

echo ""
echo "[3/6] pip install -r requirements.txt (idempotent, inside venv)"
bootstrap_pip "${PY}"
"${PY}" -m pip install -U pip wheel >/dev/null
"${PY}" -m pip install -r requirements.txt

echo ""
echo "[4/6] Stop anything bound to :8080 (best-effort)"
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8080/tcp 2>/dev/null || true
elif command -v lsof >/dev/null 2>&1; then
  kill $(lsof -t -i:8080) 2>/dev/null || true
fi
sleep 1

# Always point at this script's Redis (ignore a pre-exported REDIS_URL on :6379)
export REDIS_URL="redis://127.0.0.1:${VERIFY_REDIS_HOST_PORT}/0"

echo ""
echo "[5/6] Start control plane on 127.0.0.1:8080 (background)"
"${PY}" -m uvicorn app.main:app --host 127.0.0.1 --port 8080 &
UV_PID=$!

cleanup() {
  kill "${UV_PID}" 2>/dev/null || true
}
trap cleanup EXIT

for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:8080/health" >/dev/null; then
    break
  fi
  sleep 1
  if [[ "$i" -eq 30 ]]; then
    echo "      ERROR: /health not ready"
    exit 1
  fi
done
echo "      /health OK"

echo ""
curl -sf "http://127.0.0.1:8080/status" | "${PY}" -m json.tool

echo ""
HERMES_ENV="${HERMES_HOME:+$HERMES_HOME/.env}"
[[ -z "${HERMES_ENV}" ]] && HERMES_ENV="${HOME}/.hermes/.env"
RUN_CHAT=0
[[ -n "${OPENROUTER_API_KEY:-}${OPENAI_API_KEY:-}${ANTHROPIC_API_KEY:-}" ]] && RUN_CHAT=1
[[ -f "${HERMES_ENV}" ]] && RUN_CHAT=1

if [[ "${RUN_CHAT}" -eq 1 ]]; then
  echo "[6/6] Chat round-trip (env key and/or ${HERMES_ENV} present)"
  curl -sf -X POST "http://127.0.0.1:8080/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"Reply with exactly: OK"}],"session_id":"verify-host-1","model":"hermes"}' \
    | "${PY}" -m json.tool
  curl -sf -X DELETE "http://127.0.0.1:8080/sessions/verify-host-1" | "${PY}" -m json.tool
else
  echo "[6/6] Skip LLM test (no OPENROUTER_* / ~/.hermes/.env — configure Hermes first)"
fi

trap - EXIT
cleanup

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Done. Hermes terminal sandbox: configure on host, e.g."
echo "    hermes config set terminal.backend docker"
echo "  See: https://hermes-agent.nousresearch.com/docs/user-guide/docker"
echo ""
echo "  Manual image/container cleanup (optional):"
echo "    docker rm -f agent-runtime-redis   # frees host port ${VERIFY_REDIS_HOST_PORT}"
echo "    docker rmi hermes-runtime:latest   # old per-pod image, if present"
echo "    kind delete cluster --name hermes-runtime   # if you used Kind before"
echo "═══════════════════════════════════════════════════════════"
