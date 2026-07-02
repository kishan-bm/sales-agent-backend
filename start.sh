#!/bin/bash
set -e

# On Render, repo root = /opt/render/project/src (the backend code itself)
# But all imports use 'from backend.xxx' — create a symlink so it resolves
if [ -d /opt/render/project/src ] && [ ! -e /opt/render/project/backend ]; then
    ln -sf /opt/render/project/src /opt/render/project/backend
fi
export PYTHONPATH=/opt/render/project:$PYTHONPATH

echo "Running DB migrations..."
alembic upgrade head

echo "Starting Celery worker in background..."
celery -A backend.worker worker --loglevel=info --concurrency=2 &

echo "Starting FastAPI..."
uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
