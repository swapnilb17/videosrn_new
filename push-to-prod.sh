#!/usr/bin/env bash
# "Push to prod" — one command to ship everything to production.
# Usage: ./push-to-prod.sh                   (auto commit message)
#        ./push-to-prod.sh "your message"    (custom commit message)
set -euo pipefail

BRANCH="main"
MSG="${1:-deploy: $(date '+%Y-%m-%d %H:%M:%S')}"

echo "=== Push to Prod ==="
echo ""

if [[ -n $(git status --porcelain) ]]; then
  echo ">>> Staging all changes"
  git add -A

  echo ">>> Committing: $MSG"
  git commit -m "$MSG"
else
  echo ">>> No local changes — pushing existing commits"
fi

echo ">>> Pushing to origin/$BRANCH"
git push origin "$BRANCH"

echo ""
echo "=== Pushed. GitHub Actions will deploy automatically. ==="
echo "    Monitor: https://github.com/swapnilb17/videosrn_new/actions"
