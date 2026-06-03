from __future__ import annotations

from celery import Celery

from backend.app.config import get_settings

_settings = get_settings()

celery = Celery(
    "gitly",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
)
celery.conf.task_default_queue = "gitly"
celery.conf.broker_connection_retry_on_startup = True   # survive redis not being ready yet
# Task modules live in workers/; they are imported (and thus registered) by workers/celery.py.
