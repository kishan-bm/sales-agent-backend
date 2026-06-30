#!/bin/bash
# Runs FastAPI + Celery worker in the same Render container
set -e

echo "Running DB migrations..."
alembic upgrade head

echo "Starting Celery worker in background..."
celery -A backend.worker worker --loglevel=info --concurrency=2 &

echo "Starting FastAPI..."
uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
