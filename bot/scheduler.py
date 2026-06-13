"""
scheduler.py — APScheduler jobs (PostgreSQL version)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

import bot.db as fdb
from bot.config import TZ


async def job_eod_summary(app):
    today = datetime.now(TZ).date().isoformat()
    logger.info(f"[Scheduler] EOD summary for {today}")

    # Ambil semua sheet_urls hari ini
    urls, _ = await fdb.list_sheet_urls(date=today, limit=100000)
    
    # Cache daftar user dengan role staff
    all_users = await fdb.list_users()
    staff_ids = {u["user_id"] for u in all_users if u.get("role") == "staff"}
    
    total, ok, fail = 0, 0, 0
    from bot.services.sheet_parser import _is_ok_status
    for u in urls:
        uid_str = u.get("assigned_to")
        if not uid_str:
            continue
        try:
            uid = int(uid_str)
        except (ValueError, TypeError):
            continue
        if uid not in staff_ids:
            continue
            
        total += 1
        status = u.get("status")
        if _is_ok_status(status):
            ok += 1
        else:
            fail += 1

    admins = await fdb.list_users(role="admin")
    devs   = await fdb.list_users(role="dev")

    pct   = int(ok / total * 100) if total > 0 else 0
    text  = (
        f"📊 *RINGKASAN HARIAN — {today}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Submitted   : {total}\n"
        f"✅ OK        : {ok} ({pct}%)\n"
        f"❌ Gagal     : {fail}\n\n"
        f"_Laporan otomatis dari Stripe Verif Bot_"
    )

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
            
        from bot.handlers.verif import _sync_sheet_to_db
        
        total_synced = 0
        for task in tasks:
            try:
                count, err = await _sync_sheet_to_db(task, today)
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


async def job_local_backup():
    logger.info("[Scheduler] Starting periodic SQLite backup from PostgreSQL...")
    from bot.backup import backup_postgres_to_sqlite
    success, msg = await asyncio.to_thread(backup_postgres_to_sqlite)
    if success:
        logger.info(f"[Scheduler] {msg}")
    else:
        logger.error(f"[Scheduler] {msg}")


async def job_auto_verify_failed(app):
    today = datetime.now(TZ).date().isoformat()
    logger.info(f"[Scheduler] Starting auto-verify failed URLs for {today} WIB")
    
    try:
        from bot.services.sheet_parser import reconcile_and_verify_failed_urls
        res = await reconcile_and_verify_failed_urls(today)
        logger.info(
            f"[Scheduler] Auto-verify finished: total={res['total_failed']}, "
            f"reconciled_ok={res['sync_ok_count']}, "
            f"reverif_ok={res['reverif_ok']}, "
            f"reverif_fail={res['reverif_fail']}"
        )
    except Exception as e:
        logger.error(f"[Scheduler] Auto-verify failed job error: {e}")


async def job_deadline_reminder(app):
    from datetime import datetime
    import json
    from bot.config import TZ
    
    now = datetime.now(TZ)
    today = now.date().isoformat()
    logger.info("[Scheduler] Checking active tasks for deadline reminders...")
    
    try:
        active_tasks = await fdb.list_tasks(status="active")
        all_users = await fdb.list_users()
        staff_users = [u for u in all_users if u.get("role") == "staff" and u.get("is_active", True)]
        
        # Inisialisasi cache alert agar tidak terkirim ganda
        app.bot_data.setdefault("deadline_alerts_sent", {})
        alerts_sent = app.bot_data["deadline_alerts_sent"]
        
        # Bersihkan cache hari-hari sebelumnya agar tidak menumpuk
        keys_to_delete = [k for k in alerts_sent.keys() if not k.endswith(f"_{today}")]
        for k in keys_to_delete:
            alerts_sent.pop(k, None)
            
        for task in active_tasks:
            deadline_val = task.get("deadline")
            if not deadline_val:
                continue
                
            try:
                # deadline_val bisa berupa ISO string, misal "2026-06-13T16:00:00+07:00" atau "2026-06-13 16:00:00"
                if "T" in deadline_val:
                    deadline_dt = datetime.fromisoformat(deadline_val)
                else:
                    deadline_dt = datetime.strptime(deadline_val[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
            except Exception as e:
                logger.error(f"[Scheduler] Gagal parse deadline '{deadline_val}' untuk task {task['task_id']}: {e}")
                continue
                
            diff = deadline_dt - now
            diff_seconds = diff.total_seconds()
            
            level = None
            label = ""
            if 0 < diff_seconds <= 600:
                level = "10m"
                label = "⚠️ Kurang dari 10 Menit"
            elif 600 < diff_seconds <= 3600:
                level = "1h"
                label = "⏳ Kurang dari 1 Jam"
            elif 3600 < diff_seconds <= 7200:
                level = "2h"
                label = "⌛ Kurang dari 2 Jam"
                
            if not level:
                continue

            task_id = task["task_id"]
            quota_per_staff = task.get("quota_per_staff", 0)
            
            # Parsing list user yang di-assign
            assigned_to_raw = task.get("assigned_to", '["all"]')
            if isinstance(assigned_to_raw, str):
                try:
                    assigned_to = json.loads(assigned_to_raw)
                except Exception:
                    assigned_to = ["all"]
            else:
                assigned_to = assigned_to_raw
                
            # Filter staff yang berhak mengerjakan task ini (semua staff jika "all", atau yang spesifik di-assign)
            if "all" in assigned_to:
                target_staff = staff_users
            else:
                target_staff = [u for u in staff_users if u["user_id"] in assigned_to or str(u["user_id"]) in assigned_to]
                
            for staff in target_staff:
                user_id = staff["user_id"]
                cache_key = f"{task_id}_{user_id}_{level}_{today}"
                
                if cache_key in alerts_sent:
                    continue
                    
                # Cek progress pengerjaan staff
                prog = await fdb.get_progress(task_id, user_id, today)
                submitted = prog.get("submitted", 0) if prog else 0
                failed_count = prog.get("verified_fail", 0) if prog else 0
                
                # Cek jika belum selesai (submitted < quota_per_staff)
                if submitted < quota_per_staff:
                    remaining = quota_per_staff - submitted
                    deadline_str = deadline_dt.strftime("%d %B %Y %H:%M") + " WIB"
                    
                    status_tugas = ""
                    if submitted == 0:
                        status_tugas = "Anda belum mengklaim / mengerjakan kuota tugas hari ini."
                    else:
                        status_tugas = f"Sisa tugas Anda: {remaining} URL lagi."
                        
                    text = (
                        f"⏰ *PENGINGAT DEADLINE TASK ({level.upper()})* ⏰\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *Task*      : `{task_id}`\n"
                        f"📝 *Judul*     : {task['title']}\n"
                        f"⏰ *Deadline*  : {deadline_str}\n"
                        f"🚨 *Sisa Waktu*: *{label}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📊 *Status Progress Anda*:\n"
                        f"• Total Selesai: *{submitted}/{quota_per_staff}* URL\n"
                        f"• {status_tugas}\n"
                        f"• Gagal/Perlu Retry: *{failed_count}* URL ❌\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"Segera buka menu bot dan selesaikan verifikasi Anda! ⚡"
                    )
                    
                    try:
                        await app.bot.send_message(
                            chat_id=user_id, text=text, parse_mode="Markdown"
                        )
                        logger.info(f"[Scheduler] Sent deadline reminder ({level}) to user {user_id} for task {task_id}")
                        alerts_sent[cache_key] = True
                    except Exception as e:
                        logger.warning(f"[Scheduler] Gagal mengirim deadline reminder ke {user_id}: {e}")
                        
    except Exception as e:
        logger.error(f"[Scheduler] Error running job_deadline_reminder: {e}")


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
        job_auto_verify_failed,
        CronTrigger(minute="*/15", timezone=TZ),
        args=[app],
        id="auto_verify_failed",
        replace_existing=True,
    )

    scheduler.add_job(
        job_deadline_reminder,
        CronTrigger(minute="*/10", timezone=TZ),
        args=[app],
        id="deadline_reminder",
        replace_existing=True,
    )

    scheduler.add_job(
        job_local_backup,
        CronTrigger(hour="*/3", timezone=TZ),
        id="local_backup",
        replace_existing=True,
    )

    logger.info("[Scheduler] Jobs registered: eod_summary (22:00 WIB), sync_spreadsheets (every 30m), auto_verify_failed (every 15m), deadline_reminder (every 10m), local_backup (every 3h)")
    return scheduler
