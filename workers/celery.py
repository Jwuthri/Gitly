"""Celery worker entrypoint: `celery -A workers.celery:celery worker`.

Imports the Celery app defined in the backend and the task modules so they register.
"""
from backend.app.celery_app import celery
from workers.tasks import shrink as _shrink  # noqa: F401
from workers.tasks import trace as _trace    # noqa: F401

__all__ = ["celery"]
