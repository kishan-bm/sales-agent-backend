import ssl
from celery import Celery
from .utils.config import REDIS_URL

celery_app = Celery(
    "sales_intel",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["backend.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=1,
)

if REDIS_URL.startswith("rediss://"):
    _ssl = {"ssl_cert_reqs": ssl.CERT_NONE}
    celery_app.conf.broker_use_ssl = _ssl
    celery_app.conf.redis_backend_use_ssl = _ssl
