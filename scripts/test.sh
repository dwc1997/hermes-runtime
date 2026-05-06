#!/bin/bash
set -e

echo "═══════════════════════════════════════════"
echo "  🧪 端到端测试"
echo "═══════════════════════════════════════════"

BASE="http://localhost:30080"

# 1. 健康检查
echo ""
echo "📊 1. 健康检查..."
curl -s "$BASE/health" | python3 -m json.tool

# 2. 状态
echo ""
echo "📊 2. /status..."
curl -s "$BASE/status" | python3 -m json.tool

# 3. 聊天请求
echo ""
echo "💬 3. 发送聊天请求..."
curl -s -X POST "$BASE/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello Hermes!"}],
    "session_id": "test-session-1"
  }' | python3 -m json.tool

# 4. 状态 (应有活跃会话)
echo ""
echo "📊 4. 执行后状态..."
curl -s "$BASE/status" | python3 -m json.tool

# 5. 销毁会话
echo ""
echo "♻️  5. 销毁会话..."
curl -s -X DELETE "$BASE/sessions/test-session-1" | python3 -m json.tool

echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ 测试完成!"
echo "═══════════════════════════════════════════"
