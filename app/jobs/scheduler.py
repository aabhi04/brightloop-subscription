from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.jobs.billing_job import run_billing_job
from app.jobs.renewal_job import run_renewal_job


def start_scheduler() -> BackgroundScheduler:
    """Daily cron: plans are auto-closed at 00:05, then due subscriptions billed at 00:10."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_renewal_job, CronTrigger(hour=0, minute=5), id="renewal", coalesce=True, max_instances=1)
    scheduler.add_job(run_billing_job, CronTrigger(hour=0, minute=10), id="billing", coalesce=True, max_instances=1)
    scheduler.start()
    return scheduler
