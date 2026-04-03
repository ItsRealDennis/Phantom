"""APScheduler configuration — background jobs for scanning and settlement."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.automation.scanner import run_scan_cycle, run_crypto_scan
from src.automation.settler import auto_settle_open_trades
from src.execution.order_sync import sync_alpaca_orders, sync_all_open_trades
from src.execution.alpaca_client import is_alpaca_enabled
from src.tracking.filter_validation import settle_filtered_signals
from src.tracking.analytics import record_daily_snapshot
from src.config import CRYPTO_ENABLED

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def start_scheduler():
    """Register all jobs and start the scheduler."""

    # Stock scan: weekdays every 30 min during market hours (9:30-15:30 ET)
    scheduler.add_job(
        run_scan_cycle,
        CronTrigger(day_of_week="mon-fri", hour="9-15", minute="0,30", timezone="US/Eastern"),
        id="scan_cycle",
        name="Stock scan + analyze",
        max_instances=1,
        replace_existing=True,
    )

    # Crypto scan: 24/7 every 30 min (crypto never sleeps)
    if CRYPTO_ENABLED:
        scheduler.add_job(
            run_crypto_scan,
            CronTrigger(minute="15,45"),  # Offset from stock scans to spread load
            id="crypto_scan",
            name="Crypto scan + analyze",
            max_instances=1,
            replace_existing=True,
        )

    # Alpaca order sync: every 2 min during market hours (if enabled)
    if is_alpaca_enabled():
        scheduler.add_job(
            sync_alpaca_orders,
            CronTrigger(minute="*/2"),  # 24/7 for crypto fills
            id="alpaca_sync",
            name="Alpaca order sync",
            max_instances=1,
            replace_existing=True,
        )

    # Paper settlement: every 10 min (24/7 for crypto)
    scheduler.add_job(
        auto_settle_open_trades,
        CronTrigger(minute="*/10"),
        id="paper_settle",
        name="Paper trade settlement",
        max_instances=1,
        replace_existing=True,
    )

    # End-of-day stock settlement: weekdays at 4:05 PM ET
    scheduler.add_job(
        sync_all_open_trades,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=5, timezone="US/Eastern"),
        id="eod_settle",
        name="End-of-day settlement",
        max_instances=1,
        replace_existing=True,
    )

    # Filter validation settlement: every 10 min (same cadence as paper settlement)
    scheduler.add_job(
        settle_filtered_signals,
        CronTrigger(minute="*/10"),
        id="filter_validation",
        name="Filter validation settlement",
        max_instances=1,
        replace_existing=True,
    )

    # Daily snapshot: weekdays at 4:10 PM ET
    scheduler.add_job(
        record_daily_snapshot,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=10, timezone="US/Eastern"),
        id="daily_snapshot",
        name="Daily snapshot recording",
        max_instances=1,
        replace_existing=True,
    )

    # Crypto daily snapshot: midnight UTC (crypto has no close)
    if CRYPTO_ENABLED:
        scheduler.add_job(
            record_daily_snapshot,
            CronTrigger(hour=0, minute=5),
            id="daily_snapshot_crypto",
            name="Crypto daily snapshot",
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
