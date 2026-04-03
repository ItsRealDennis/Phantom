"""APScheduler configuration — background jobs for scanning and settlement."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.automation.scanner import run_scan_cycle
from src.automation.settler import auto_settle_open_trades
from src.execution.order_sync import sync_alpaca_orders, sync_all_open_trades
from src.execution.alpaca_client import is_alpaca_enabled

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

    # Alpaca order sync: every 5 min during market hours (if enabled)
    if is_alpaca_enabled():
        scheduler.add_job(
            sync_alpaca_orders,
            CronTrigger(day_of_week="mon-fri", hour="9-15", minute="*/5", timezone="US/Eastern"),
            id="alpaca_sync",
            name="Alpaca order sync",
            max_instances=1,
            replace_existing=True,
        )

    # Paper settlement: weekdays every 30 min during market hours
    scheduler.add_job(
        auto_settle_open_trades,
        CronTrigger(day_of_week="mon-fri", hour="9-15", minute="0,30", timezone="US/Eastern"),
        id="paper_settle",
        name="Paper trade settlement",
        max_instances=1,
        replace_existing=True,
    )

    # End-of-day combined sync: weekdays at 4:05 PM ET
    scheduler.add_job(
        sync_all_open_trades,
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
