import logging

from app.db import SessionLocal
from app.services.plan_service import auto_close_expired_plans

logger = logging.getLogger("brightloop.jobs")


def run_renewal_job() -> int:
    """Daily job: close plans with auto_close=True whose end date has passed."""
    with SessionLocal() as db:
        closed = auto_close_expired_plans(db)
    logger.info("renewal job: %d plans auto-closed", closed)
    return closed
