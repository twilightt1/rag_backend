from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "rag_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.email_tasks",
        "app.tasks.ingestion_tasks",
        "app.tasks.quota_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "tasks.send_verification_email":    {"queue": "email"},
        "tasks.send_password_reset_email":  {"queue": "email"},
        "tasks.process_document":           {"queue": "ingestion"},
        "tasks.reset_daily_quotas":         {"queue": "default"},
    },
    beat_schedule={
        "reset-daily-quotas": {
            "task":     "tasks.reset_daily_quotas",
            "schedule": crontab(hour=0, minute=0),
        },
    },
)
