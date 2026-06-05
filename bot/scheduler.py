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


def setup_scheduler(app) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=str(TZ))

    scheduler.add_job(
        job_eod_summary,
        CronTrigger(hour=22, minute=0, timezone=TZ),
        args=[app],
        id="eod_summary",
        replace_existing=True,
    )

    logger.info("[Scheduler] Jobs registered: eod_summary (22:00 WIB)")
    return scheduler
