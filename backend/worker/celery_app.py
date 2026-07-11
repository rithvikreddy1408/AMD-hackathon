"""
Celery application factory.
Broker and result backend both use Redis so we need only one extra service.
"""
from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

celery_app = Celery(
    "incident_mesh",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["backend.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Retry failed tasks up to 3 times with exponential back-off
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
