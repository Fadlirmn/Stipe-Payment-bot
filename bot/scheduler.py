"""
scheduler.py — APScheduler jobs (Firebase version)
"""
from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

import bot.firebase_db as fdb
from bot.config import TZ


async def job_eod_summary(app):
    today = datetime.now(TZ).date().isoformat()
    logger.info(f"[Scheduler] EOD summary for {today}")

    tasks = await fdb.list_tasks()
    total, ok, pending = 0, 0, 0
    for task in tasks:
        t = await fdb.count_sheet_urls(task["task_id"], today)
        o = await fdb.count_sheet_urls(task["task_id"], today, status="OK")
        p = await fdb.count_sheet_urls(task["task_id"], today, status="PENDING")
        total += t; ok += o; pending += p

    pct   = int(ok / total * 100) if total > 0 else 0
    text  = (
        f"📊 *RINGKASAN HARIAN — {today}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Total URL   : {total}\n"
        f"✅ Verified  : {ok} ({pct}%)\n"
        f"⚪ Pending   : {pending}\n"
        f"❌ Gagal     : {total - ok - pending}\n\n"
        f"_Laporan otomatis dari Stripe Verif Bot_"
    )

    admins = await fdb.list_users(role="admin")
    devs   = await fdb.list_users(role="dev")
    for u in admins + devs:
        try:
            await app.bot.send_message(
                chat_id=u["user_id"], text=text, parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"[Scheduler] Gagal kirim EOD ke {u['user_id']}: {e}")


async def job_sync_spreadsheets(app):
    today = datetime.now(TZ).date().isoformat()
    logger.info(f"[Scheduler] Starting auto-sync spreadsheets for {today}")
    
    try:
        tasks = await fdb.list_tasks(status="active")
        if not tasks:
            logger.info("[Scheduler] No active tasks to sync.")
            return
            
        from bot.handlers.verif import _sync_sheet_to_firebase
        
        total_synced = 0
        for task in tasks:
            try:
                count, err = await _sync_sheet_to_firebase(task, today)
                if err:
                    logger.error(f"[Scheduler] Sync failed for task {task['task_id']}: {err}")
                else:
                    logger.info(f"[Scheduler] Synced {count} URLs for task {task['task_id']}")
                    total_synced += count
            except Exception as e:
                logger.error(f"[Scheduler] Error syncing task {task['task_id']}: {e}")
                
        logger.info(f"[Scheduler] Auto-sync finished. Total URLs synced: {total_synced}")
    except Exception as e:
        logger.error(f"[Scheduler] Auto-sync job error: {e}")


async def job_local_backup(app):
    logger.info("[Scheduler] Starting local SQLite backup...")
    from bot.backup import backup_firestore_to_sqlite
    success, msg = await backup_firestore_to_sqlite()
    if success:
        logger.info(f"[Scheduler] Backup success: {msg}")
    else:
        logger.error(f"[Scheduler] Backup failed: {msg}")


def setup_scheduler(app) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=str(TZ))

    scheduler.add_job(
        job_eod_summary,
        CronTrigger(hour=22, minute=0, timezone=TZ),
        args=[app],
        id="eod_summary",
        replace_existing=True,
    )

    scheduler.add_job(
        job_sync_spreadsheets,
        CronTrigger(minute="*/30", timezone=TZ),
        args=[app],
        id="sync_spreadsheets",
        replace_existing=True,
    )

    scheduler.add_job(
        job_local_backup,
        CronTrigger(hour="*/3", timezone=TZ),
        args=[app],
        id="local_backup",
        replace_existing=True,
    )

    logger.info("[Scheduler] Jobs registered: eod_summary (22:00 WIB), sync_spreadsheets (every 30m), local_backup (every 3h)")
    return scheduler
