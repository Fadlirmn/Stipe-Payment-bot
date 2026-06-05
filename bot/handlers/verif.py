"""
handlers/verif.py — Alur verifikasi URL dari Google Sheets (Firebase version)
"""
from __future__ import annotations

from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import bot.firebase_db as fdb
from bot.middlewares.auth import get_or_create_user, require_approved
from bot.services.sheet_parser import fetch_today_urls
from bot.services.url_verifier import verify_url
from bot.utils.keyboards import task_list_keyboard, url_action_keyboard, back_keyboard
from bot.utils.formatters import progress_bar, now_wib, status_badge
from bot.config import TZ


@require_approved
async def cmd_verif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = await fdb.list_tasks(status="active")
    if not tasks:
        await update.effective_message.reply_text(
            "📭 *Belum ada task aktif.*\nAdmin perlu membuat task terlebih dahulu.",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )
        return

    await update.effective_message.reply_text(
        "🔗 *VERIFIKASI URL HARI INI*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Pilih task untuk memulai verifikasi:",
        parse_mode="Markdown",
        reply_markup=task_list_keyboard(tasks),
    )



async def cb_task_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    task_id = update.callback_query.data.split(":")[2]
    user    = await get_or_create_user(update)
    today   = datetime.now(TZ).date().isoformat()

    task = await fdb.get_task(task_id)
    if not task:
        await update.callback_query.message.reply_text("❌ Task tidak ditemukan.")
        return

    existing_count = await fdb.count_sheet_urls(task_id, today)
    if existing_count == 0:
        await update.callback_query.message.reply_text(
            f"⏳ Mengambil URL dari spreadsheet untuk tanggal *{today}*...",
            parse_mode="Markdown",
        )
        await _sync_sheet_to_firebase(task, today)

    await _show_next_pending_url(update, context, task_id, user["user_id"], today)


async def _sync_sheet_to_firebase(task: dict, target_date: str) -> int:
    from datetime import date
    tab = task.get("sheet_tab", "Sheet1")
    try:
        rows = fetch_today_urls(tab_name=tab, target_date=date.fromisoformat(target_date))
    except Exception as exc:
        return 0

    count = 0
    for row in rows:
        await fdb.add_sheet_url(
            task_id=task["task_id"],
            date=target_date,
            account=row["account"],
            payment_url=row["payment_url"],
            notes=row["notes"],
        )
        count += 1
    return count


async def _show_next_pending_url(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    task_id: str,
    user_id: int,
    today: str,
):
    url_obj = await fdb.get_next_pending_url(task_id, today)

    if not url_obj:
        total   = await fdb.count_sheet_urls(task_id, today)
        ok      = await fdb.count_sheet_urls(task_id, today, status="OK")
        text = (
            f"🎉 *Semua URL telah diproses!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Task : {task_id}\n"
            f"Total: {total} URL\n"
            f"✅ Valid : {ok}\n"
            f"❌ Gagal : {total - ok}\n\n"
            f"Terima kasih telah menyelesaikan verifikasi hari ini! 🙌"
        )
        msg = update.callback_query.message if update.callback_query else update.message
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=back_keyboard())
        return

    total = await fdb.count_sheet_urls(task_id, today)
    done  = await fdb.count_sheet_urls(task_id, today, status="OK")
    bar   = progress_bar(done, total)

    text = (
        f"🔗 *VERIFIKASI URL*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Task     : `{task_id}`\n"
        f"📅 Tanggal  : {today}\n"
        f"📊 Progress : {bar}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Akun     : {url_obj.get('account') or '-'}\n"
        f"📝 Catatan  : {url_obj.get('notes') or '-'}\n\n"
        f"🔗 URL:\n`{url_obj['payment_url']}`\n\n"
        f"Klik *Verifikasi Sekarang* untuk memeriksa URL ini."
    )
    kb  = url_action_keyboard(url_obj["id"])
    msg = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await msg.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cb_url_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("⏳ Memeriksa URL...")
    doc_id = update.callback_query.data.split(":")[2]
    user   = await get_or_create_user(update)

    url_obj = await fdb.get_sheet_url(doc_id)
    if not url_obj:
        await update.callback_query.message.reply_text("❌ URL tidak ditemukan.")
        return

    payment_url = url_obj["payment_url"]
    task_id     = url_obj["task_id"]
    today       = url_obj["date"]

    result = await verify_url(payment_url)

    await fdb.update_sheet_url(doc_id,
        status=result.status.value,
        http_code=result.http_code,
        error_msg=result.message if not result.is_ok else None,
        verified_by=user["user_id"],
        verified_at=now_wib().isoformat(),
    )

    await fdb.upsert_progress(
        task_id=task_id, user_id=user["user_id"], date=today,
        submitted_delta=1,
        ok_delta=1 if result.is_ok else 0,
        fail_delta=0 if result.is_ok else 1,
    )

    await fdb.add_audit_log(
        actor_id=user["user_id"], action="url.verify",
        target_type="sheet_url", target_id=doc_id,
        detail={"url": payment_url, "status": result.status.value,
                "http_code": result.http_code},
    )

    await update.callback_query.message.reply_text(
        f"{result.emoji} *Hasil Verifikasi*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Status : {status_badge(result.status.value)}\n"
        f"HTTP   : {result.http_code or '-'}\n"
        f"Pesan  : {result.message}\n"
        f"URL    : `{payment_url[:60]}...`",
        parse_mode="Markdown",
    )
    await _show_next_pending_url(update, context, task_id, user["user_id"], today)


async def cb_url_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("⏭️ URL dilewati")
    doc_id = update.callback_query.data.split(":")[2]
    user   = await get_or_create_user(update)

    url_obj = await fdb.get_sheet_url(doc_id)
    if url_obj:
        await fdb.update_sheet_url(doc_id,
            status="SKIPPED",
            verified_by=user["user_id"],
            verified_at=now_wib().isoformat(),
        )
        await _show_next_pending_url(
            update, context, url_obj["task_id"], user["user_id"], url_obj["date"]
        )


async def cb_menu_sync_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = await get_or_create_user(update)
    if user.get("role") not in ("admin", "dev"):
        await update.callback_query.message.reply_text("🚫 Akses ditolak.")
        return

    today = datetime.now(TZ).date().isoformat()
    tasks = await fdb.list_tasks(status="active")
    total_synced = 0
    for task in tasks:
        n = await _sync_sheet_to_firebase(task, today)
        total_synced += n

    await update.callback_query.message.reply_text(
        f"✅ *Sync selesai!*\n{total_synced} URL baru ditambahkan dari spreadsheet.",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )


def get_handlers():
    return [
        CommandHandler("verif",  cmd_verif),
        CallbackQueryHandler(cb_task_select,     pattern=r"^task:select:.+$"),
        CallbackQueryHandler(cb_url_verify,      pattern=r"^url:verify:.+$"),
        CallbackQueryHandler(cb_url_skip,        pattern=r"^url:skip:.+$"),
        CallbackQueryHandler(cb_menu_sync_sheet, pattern="^menu:sync_sheet$"),
    ]
