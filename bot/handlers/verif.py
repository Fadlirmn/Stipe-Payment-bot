"""
handlers/verif.py — Alur verifikasi URL dari Google Sheets (Firebase version)
"""
from __future__ import annotations

from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import bot.firebase_db as fdb
from bot.middlewares.auth import get_or_create_user, require_approved
from bot.services.sheet_parser import fetch_today_urls, update_sheet_status
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

    # Check quota per staff harian
    quota_staff = task.get("quota_per_staff", 0)
    if quota_staff > 0:
        prog = await fdb.get_progress(task_id, user["user_id"], today)
        submitted = prog.get("submitted", 0) if prog else 0
        if submitted >= quota_staff:
            await update.callback_query.message.reply_text(
                f"⚠️ *Kuota Staff Terpenuhi!*\n"
                f"Anda telah memproses {submitted}/{quota_staff} URL untuk task ini hari ini.\n\n"
                f"Terima kasih atas kerja kerasnya! 🙌",
                parse_mode="Markdown",
                reply_markup=back_keyboard()
            )
            return

    existing_count = await fdb.count_sheet_urls(task_id, today)
    if existing_count == 0:
        await update.callback_query.message.reply_text(
            f"⏳ Mengambil URL dari spreadsheet untuk tanggal *{today}*...",
            parse_mode="Markdown",
        )
        count, err = await _sync_sheet_to_firebase(task, today)
        if err:
            await update.callback_query.message.reply_text(
                f"❌ *Gagal mengambil URL dari Sheet:*\n`{err}`\n\n"
                f"Pastikan URL Google Apps Script (`APPS_SCRIPT_URL`) di .env sudah benar dan dideploy.",
                parse_mode="Markdown"
            )
            return
        if count == 0:
            await update.callback_query.message.reply_text(
                f"⚠️ *Tidak ditemukan URL aktif untuk tanggal {today}* di Sheet Anda.\n"
                f"Pastikan kolom Timestamp/Date berisi tanggal hari ini.",
                parse_mode="Markdown",
                reply_markup=back_keyboard()
            )
            return

    await _show_next_pending_url(update, context, task_id, user["user_id"], today)


async def _sync_sheet_to_firebase(task: dict, target_date: str) -> tuple[int, str | None]:
    from datetime import date
    tab = task.get("sheet_tab", "Sheet1")
    try:
        rows = fetch_today_urls(tab_name=tab, target_date=date.fromisoformat(target_date))
    except Exception as exc:
        logger.error(f"[Sync] Error fetching URLs for task {task['task_id']}: {exc}")
        return 0, str(exc)

    count = 0
    for row in rows:
        await fdb.add_sheet_url(
            task_id=task["task_id"],
            date=target_date,
            account=row["account"],
            payment_url=row["payment_url"],
            notes=row["notes"],
        )
        # Tandai sebagai ASSIGNED di Google Sheet
        await update_sheet_status(row["payment_url"], "ASSIGNED", tab_name=tab)
        count += 1
    return count, None


async def _show_next_pending_url(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    task_id: str,
    user_id: int,
    today: str,
):
    task = await fdb.get_task(task_id)
    # Check quota per staff harian sebelum mengambil URL baru
    quota_staff = task.get("quota_per_staff", 0) if task else 0
    if quota_staff > 0:
        prog = await fdb.get_progress(task_id, user_id, today)
        submitted = prog.get("submitted", 0) if prog else 0
        if submitted >= quota_staff:
            text = (
                f"⚠️ *Kuota Staff Terpenuhi!*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Anda telah memproses {submitted}/{quota_staff} URL untuk task ini hari ini.\n\n"
                f"Terima kasih atas kerja kerasnya! 🙌"
            )
            msg = update.callback_query.message if update.callback_query else update.message
            await msg.reply_text(text, parse_mode="Markdown", reply_markup=back_keyboard())
            return

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

    # Kirim update status ke Google Sheet beserta info staff
    staff_identifier = f"@{user.get('username')}" if user.get('username') else f"{user.get('full_name') or user['user_id']}"
    sheet_status = f"{'SUCCESS' if result.is_ok else 'FAILED'} ({staff_identifier})"
    task = await fdb.get_task(task_id)
    tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"
    await update_sheet_status(payment_url, sheet_status, tab_name=tab)

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

        # Kirim update status ke Google Sheet beserta info staff
        staff_identifier = f"@{user.get('username')}" if user.get('username') else f"{user.get('full_name') or user['user_id']}"
        sheet_status = f"SKIPPED ({staff_identifier})"
        task = await fdb.get_task(url_obj["task_id"])
        tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"
        await update_sheet_status(url_obj["payment_url"], sheet_status, tab_name=tab)

        await _show_next_pending_url(
            update, context, url_obj["task_id"], user["user_id"], url_obj["date"]
        )


async def cb_menu_sync_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = await get_or_create_user(update)
    if user.get("role") not in ("admin", "dev"):
        await update.effective_message.reply_text("🚫 Akses ditolak.")
        return

    today = datetime.now(TZ).date().isoformat()
    tasks = await fdb.list_tasks(status="active")
    if not tasks:
        await update.effective_message.reply_text(
            "📭 Tidak ada task aktif untuk disinkronisasi.",
            reply_markup=back_keyboard()
        )
        return

    report_lines = [f"🔄 *SYNC SPREADSHEET — {today}*\n━━━━━━━━━━━━━━━━━━━━"]
    total_synced = 0
    for task in tasks:
        count, err = await _sync_sheet_to_firebase(task, today)
        if err:
            report_lines.append(f"📌 `{task['task_id']}`: ❌ Error: `{err}`")
        else:
            report_lines.append(f"📌 `{task['task_id']}` ({task['title'][:15]}...): ✅ Sync {count} URL")
            total_synced += count

    report_lines.append(f"\nTotal URL baru disinkronisasi: *{total_synced}*")
    await update.effective_message.reply_text(
        "\n".join(report_lines),
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
