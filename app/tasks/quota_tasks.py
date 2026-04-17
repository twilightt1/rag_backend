import logging
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="tasks.reset_daily_quotas")
def reset_daily_quotas() -> None:
    """Reset daily request counters — runs at midnight UTC via Celery Beat."""
    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import Session
    from app.config import settings
    from app.models.user_quota import UserQuota
    import datetime

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine   = create_engine(sync_url, pool_pre_ping=True)
    with Session(engine) as db:
        db.execute(
            update(UserQuota).values(
                requests_today=0,
                tokens_today=0,
                last_daily_reset=datetime.date.today(),
            )
        )
        db.commit()
    log.info("Daily quotas reset")
