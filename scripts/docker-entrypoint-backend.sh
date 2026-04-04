#!/usr/bin/env bash
set -euo pipefail

echo "⏳ Waiting for PostgreSQL at ${DB_HOST:-db}:${DB_PORT:-5432}..."

until pg_isready -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${POSTGRES_USER:-avatar_app}" -q; do
  sleep 1
done

echo "✅ PostgreSQL is ready"

echo "🔄 Running Alembic migrations..."
cd /opt/backend
alembic upgrade head
echo "✅ Migrations complete"

echo "🚀 Starting FastAPI..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips='*'
