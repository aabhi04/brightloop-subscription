import logging

from app.db import SessionLocal
from app.services.billing_service import generate_due_invoices

logger = logging.getLogger("brightloop.jobs")


def run_billing_job() -> dict:
    """Daily job: same service as POST /api/invoices/generate-due."""
    with SessionLocal() as db:
        result = generate_due_invoices(db)
    logger.info("billing job: %s", result)
    return result
