#!/usr/bin/env bash
# Prepare repo and set remote. Create an EMPTY GitHub repo first (no README).
#
# Usage:
#   bash scripts/github-first-push.sh
#   bash scripts/github-first-push.sh https://github.com/YOU/other-repo.git
#   git push -u origin main
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DEFAULT_REMOTE="https://github.com/dwc1997/hermes-runtime.git"
REMOTE="${1:-$DEFAULT_REMOTE}"

if [[ ! -d .git ]]; then
  git init
  git branch -M main
fi

git add -A
if git diff --cached --quiet 2>/dev/null; then
  echo "Nothing staged (already committed?)."
else
  git commit -m "Initial commit: Hermes host runtime gateway"
fi

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE"
else
  git remote add origin "$REMOTE"
fi

echo ""
echo "Remote set to: $REMOTE"
echo "Push:"
echo "  git push -u origin main"
