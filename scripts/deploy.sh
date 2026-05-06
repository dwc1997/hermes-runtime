#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "═══════════════════════════════════════════"
echo "  Agent Runtime deploy (host Hermes in API pod)"
echo "═══════════════════════════════════════════"

echo ""
echo "📦 Step 1: Build control-plane image (includes hermes-agent)..."
docker build -t agent-runtime:latest -f "$ROOT_DIR/Dockerfile" "$ROOT_DIR"

echo ""
echo "📥 Step 2: Load image into kind..."
kind load docker-image agent-runtime:latest --name hermes-runtime

echo ""
echo "☸️  Step 3: Apply manifests..."
kubectl apply -f "$ROOT_DIR/k8s/namespace.yaml"
kubectl apply -f "$ROOT_DIR/k8s/rbac.yaml"
kubectl apply -f "$ROOT_DIR/k8s/secret.yaml"
kubectl apply -f "$ROOT_DIR/k8s/redis.yaml"
kubectl apply -f "$ROOT_DIR/k8s/control-plane.yaml"

echo ""
echo "⏳ Step 4: Wait for pods..."
kubectl -n hermes-runtime wait --for=condition=ready pod -l app=control-plane --timeout=180s
kubectl -n hermes-runtime wait --for=condition=ready pod -l app=redis --timeout=60s

echo ""
echo "═══════════════════════════════════════════"
echo "  Done."
echo "  API: http://localhost:30080/v1/chat/completions"
echo "  (Legacy hermes-runtime per-session image is no longer used.)"
echo "═══════════════════════════════════════════"
