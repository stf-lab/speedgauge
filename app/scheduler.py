"""APScheduler-based test scheduler."""
import asyncio
import logging
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import get_config, get_db_path
from database import save_result, cleanup_old_results
from speedtest_runner import run_speedtest, get_status
from mqtt_ha import publish_state, publish_running
from notifications import notify

logger = logging.getLogger("speed_monitor.scheduler")

_scheduler: BackgroundScheduler | None = None
_event_loop = None


def set_event_loop(loop):
    global _event_loop
    _event_loop = loop


def _run_test_job():
    """Execute a speedtest (called by scheduler or manual trigger)."""
    status = get_status()
    if status["running"]:
        logger.warning("Test already running, skipping scheduled run")
        return

    config = get_config()
    server_id = config.get("server_id", "").strip() or None

    try:
        publish_running(True, config)
        result = run_speedtest(server_id=server_id)
        save_result(result)
        publish_state(result, config)

        # Send notifications
        if _event_loop:
            asyncio.run_coroutine_threadsafe(notify(result, config), _event_loop)

        # Cleanup old results
        retention = int(config.get("retention_days", 0))
        if retention > 0:
            deleted = cleanup_old_results(retention)
            if deleted:
                logger.info("Cleaned up %d old results", deleted)

        logger.info(
            "Test complete: %.1f/%.1f Mbps, ping %.1f ms",
            result["download_mbps"], result["upload_mbps"], result["ping_ms"],
        )
    except Exception as e:
        logger.error("Speedtest failed: %s", e)
    finally:
        publish_running(False, config)


def run_test_now():
    """Trigger an immediate test in a background thread."""
    thread = threading.Thread(target=_run_test_job, daemon=True)
    thread.start()


def _make_cron_trigger(interval_minutes: int, timezone: str = "Europe/Paris") -> CronTrigger:
    """Build a CronTrigger that fires at clock-aligned times.

    Examples:
        10 min  -> :00, :10, :20, :30, :40, :50
        15 min  -> :00, :15, :30, :45
        30 min  -> :00, :30
        60 min  -> every hour at :00
        120 min -> every 2 hours at :00
        180 min -> every 3 hours at :00
        1440 min -> once a day at 00:00
    """
    if interval_minutes < 60:
        return CronTrigger(minute=f"*/{interval_minutes}", timezone=timezone)
    hours = interval_minutes // 60
    return CronTrigger(minute="0", hour=f"*/{hours}", timezone=timezone)


def start():
    """Start the scheduler."""
    global _scheduler
    config = get_config()
    interval = int(config.get("interval_minutes", 60))
    tz = config.get("timezone", "Europe/Paris")

    _scheduler = BackgroundScheduler(timezone=tz)
    _scheduler.add_job(
        _run_test_job,
        trigger=_make_cron_trigger(interval, tz),
        id="speedtest_job",
        name="Scheduled Speed Test",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started: test every %d minutes (clock-aligned)", interval)


def reschedule(interval_minutes: int):
    """Update the test interval without restarting."""
    if _scheduler:
        config = get_config()
        tz = config.get("timezone", "Europe/Paris")
        _scheduler.reschedule_job(
            "speedtest_job",
            trigger=_make_cron_trigger(interval_minutes, tz),
        )
        logger.info("Rescheduled to every %d minutes (clock-aligned)", interval_minutes)


def stop():
    """Stop the scheduler."""
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
