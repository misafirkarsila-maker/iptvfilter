"""Otomatik günlük senkronizasyon (APScheduler)."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from . import config
from .database import SessionLocal
from .models import Provider
from .sync_service import sync_provider

logger = logging.getLogger(__name__)


def run_sync_all() -> dict:
    """Tüm sağlayıcıları senkronize et (manuel buton + cron ortak)."""
    db = SessionLocal()
    results = {}
    try:
        providers = db.query(Provider).all()
        for provider in providers:
            try:
                results[provider.name] = sync_provider(db, provider)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Sync başarısız: %s", provider.name)
                results[provider.name] = {"status": "error", "error": str(exc)}
    finally:
        db.close()
    return results


scheduler = BackgroundScheduler()


def start_scheduler() -> None:
    if scheduler.running:
        return

    cron_fields = config.SYNC_CRON.split()
    if len(cron_fields) != 5:
        logger.warning(
            "SYNC_CRON geçersiz '%s', varsayılan '0 3 * * *' kullanılacak.",
            config.SYNC_CRON,
        )
        cron_fields = ["0", "3", "*", "*", "*"]

    schedule_cron = {
        "minute": cron_fields[0],
        "hour": cron_fields[1],
        "day": cron_fields[2],
        "month": cron_fields[3],
        "day_of_week": cron_fields[4],
    }
    scheduler.add_job(
        run_sync_all,
        trigger="cron",
        **schedule_cron,
        id="daily_sync",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Scheduler başlatıldı (cron: %s)", config.SYNC_CRON)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
