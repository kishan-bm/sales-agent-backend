#!/bin/bash
set -e

# On Render, repo root = /opt/render/project/src (the backend code itself)
# But all imports use 'from backend.xxx' — create a symlink so it resolves
if [ -d /opt/render/project/src ] && [ ! -e /opt/render/project/backend ]; then
    ln -sf /opt/render/project/src /opt/render/project/backend
fi
export PYTHONPATH=/opt/render/project:$PYTHONPATH

echo "Running DB migrations..."
# Debug: show which DB host we're connecting to (password hidden)
python3 -c "
import os
url = os.getenv('DATABASE_URL', 'NOT SET')
if '@' in url:
    parts = url.split('@')
    print('DB URL host:', parts[-1])
    creds = parts[0].split('://')[-1]
    user = creds.split(':')[0]
    print('DB user:', user)
else:
    print('DATABASE_URL:', url)
"
alembic upgrade head

echo "Starting Celery worker in background..."
celery -A backend.worker worker --loglevel=info --concurrency=2 &

echo "Starting FastAPI..."
uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
