"""APScheduler configuration — background jobs for scanning and settlement."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.automation.scanner import run_scan_cycle
from src.automation.settler import auto_settle_open_trades

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def start_scheduler():
    """Register all jobs and start the scheduler."""

    # Scan job: weekdays at 10:00 AM and 2:00 PM ET
    scheduler.add_job(
        run_scan_cycle,
        CronTrigger(day_of_week="mon-fri", hour="10,14", minute=0, timezone="US/Eastern"),
        id="scan_cycle",
        name="Market scan + analyze",
        max_instances=1,
        replace_existing=True,
    )

    # Settlement check: weekdays every 30 min during market hours (9:30-15:30 ET)
    scheduler.add_job(
        auto_settle_open_trades,
        CronTrigger(day_of_week="mon-fri", hour="9-15", minute="0,30", timezone="US/Eastern"),
        id="auto_settle",
        name="Auto-settle open trades",
        max_instances=1,
        replace_existing=True,
    )

    # End-of-day settlement: weekdays at 4:05 PM ET
    scheduler.add_job(
        auto_settle_open_trades,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=5, timezone="US/Eastern"),
        id="eod_settle",
        name="End-of-day settlement",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
    for job in scheduler.get_jobs():
        logger.info("  Job '%s' — next run: %s", job.name, job.next_run_time)


def stop_scheduler():
    """Shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def get_scheduler_status() -> list[dict]:
    """Return status of all scheduled jobs."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return jobs
