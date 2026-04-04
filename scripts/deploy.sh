#!/usr/bin/env bash
# Runs ON THE SERVER after git pull. Rebuilds and restarts Docker containers.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ec2-user/enably-vgen}"

cd "$APP_DIR"

echo ">>> Pulling latest code"
git pull --ff-only

echo ">>> Rebuilding containers (no cache for code layers)"
docker compose build --pull

echo ">>> Restarting services"
docker compose up -d --remove-orphans

echo ">>> Cleaning old images"
docker image prune -f

echo ">>> Checking service health"
sleep 5
docker compose ps

echo ">>> Deploy complete"
