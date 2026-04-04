#!/usr/bin/env bash
# Run on the EC2 host after you push from Cursor (see docs/DEPLOY_WORKFLOW.md).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/avatar-video-creator}"
VENV="${VENV:-$APP_DIR/.venv}"
SERVICE="${SERVICE:-avatar-video-creator}"

cd "$APP_DIR"

echo ">>> git pull"
git pull --ff-only

echo ">>> venv + pip"
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
# shellcheck source=/dev/null
source "$VENV/bin/activate"
pip install -U pip
if [[ "${SKIP_COQUI:-0}" == "1" ]]; then
  pip install -e "."
else
  pip install -e ".[coqui]"
fi

if [[ "${SKIP_ALEMBIC:-0}" != "1" ]]; then
  echo ">>> alembic upgrade head"
  alembic upgrade head
fi

echo ">>> restart $SERVICE"
sudo systemctl restart "$SERVICE"
sudo systemctl --no-pager status "$SERVICE" || true

echo ">>> done"
