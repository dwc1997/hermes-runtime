#!/bin/bash
set -e

echo "═══════════════════════════════════════════"
echo "  🏗️  Kind 集群创建脚本"
echo "═══════════════════════════════════════════"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# 检查 kind
if ! command -v kind &> /dev/null; then
    echo "❌ kind 未安装，正在安装..."
    curl -Lo /tmp/kind https://kind.sigs.k8s.io/dl/v0.27.0/kind-linux-amd64
    chmod +x /tmp/kind
    sudo mv /tmp/kind /usr/local/bin/kind
    echo "✅ kind 已安装"
fi

# 检查 kubectl
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl 未安装，正在安装..."
    curl -Lo /tmp/kubectl "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
    chmod +x /tmp/kubectl
    sudo mv /tmp/kubectl /usr/local/bin/kubectl
    echo "✅ kubectl 已安装"
fi

# 删除旧集群
kind delete cluster --name hermes-runtime 2>/dev/null || true

# 创建集群
echo ""
echo "☸️  创建 kind 集群..."
kind create cluster --config "$ROOT_DIR/k8s/kind-config.yaml"

echo ""
echo "✅ 集群就绪!"
kubectl cluster-info --context kind-hermes-runtime
