"""
handlers/verif.py — Alur verifikasi URL dari Google Sheets (Firebase version)
"""
from __future__ import annotations

from datetime import datetime
import asyncio
from loguru import logger

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import bot.db as fdb
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

    # Kalau task aktif cuma 1, langsung tampilkan menu opsi task
    if len(tasks) == 1:
        user  = await get_or_create_user(update)
        today = datetime.now(TZ).date().isoformat()
        await _show_task_options_menu(update, context, tasks[0], user, today)
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
            f"⚠️ *Belum ada URL untuk tanggal {today}* di database.\n"
            f"Silakan hubungi Admin untuk melakukan sinkronisasi spreadsheet terlebih dahulu.",
            parse_mode="Markdown",
            reply_markup=back_keyboard()
        )
        return

    await _show_task_options_menu(update, context, task, user, today)


async def _sync_sheet_to_firebase(task: dict, target_date: str) -> tuple[int, str | None]:
    from datetime import date
    import hashlib

    tab = task.get("sheet_tab", "Sheet1")
    task_id = task["task_id"]

    try:
        rows = await fetch_today_urls(tab_name=tab, target_date=date.fromisoformat(target_date))
    except Exception as exc:
        logger.error(f"[Sync] Error fetching URLs for task {task_id}: {exc}")
        return 0, str(exc)

    if not rows:
        return 0, None

    # ── Ambil existing doc IDs agar tidak double-insert ──
    existing_ids: set | None = None
    try:
        pg_urls, _ = await fdb.list_sheet_urls(
            task_id=task_id, date=target_date, status=None, limit=10000, offset=0
        )
        existing_ids = {u["id"] for u in pg_urls}
    except Exception as e:
        logger.warning(f"[Sync] Failed to fetch existing IDs: {e}. Falling back to individual check.")
        existing_ids = None

    count = 0
    for row in rows:
        doc_id = hashlib.md5(f"{task_id}_{row['payment_url']}".encode("utf-8")).hexdigest()
        if existing_ids is not None and doc_id in existing_ids:
            continue

        await fdb.add_sheet_url(
            task_id=task_id,
            date=target_date,
            account=row["account"],
            payment_url=row["payment_url"],
            notes=row["notes"],
            check_exists=(existing_ids is None),
        )
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

    url_obj, claimed_urls = await fdb.get_or_claim_next_url(task_id, today, user_id)

    if claimed_urls:
        user_data = await fdb.get_user(user_id)
        username = user_data.get("username") if user_data else None
        full_name = user_data.get("full_name") if user_data else None
        staff_str = f"@{username}" if username else (full_name if full_name else str(user_id))
        status_str = f"ASSIGNED - {staff_str}"
        tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"

        sem = asyncio.Semaphore(5)
        async def safe_update(u):
            async with sem:
                try:
                    await update_sheet_status(u["payment_url"], status_str, tab_name=tab, staff_info=staff_str)
                except Exception as e:
                    logger.error(f"[SheetUpdate] Gagal update status Google Sheet untuk {u['payment_url']}: {e}")

        # Jalankan update secara paralel
        await asyncio.gather(*(safe_update(u) for u in claimed_urls), return_exceptions=True)

    if not url_obj:
        total   = await fdb.count_sheet_urls(task_id, today)
        pending = await fdb.count_sheet_urls(task_id, today, status="PENDING")
        processing = await fdb.count_sheet_urls(task_id, today, status="PROCESSING")
        done = max(0, total - pending - processing)
        ok      = await fdb.count_sheet_urls(task_id, today, status="OK")
        text = (
            f"🎉 *Semua URL telah diproses!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Task : {task_id}\n"
            f"Total: {total} URL\n"
            f"✅ Valid : {ok}\n"
            f"❌ Lainnya: {done - ok}\n\n"
            f"Terima kasih telah menyelesaikan verifikasi hari ini! 🙌"
        )
        msg = update.callback_query.message if update.callback_query else update.message
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=back_keyboard())
        return

    total = await fdb.count_sheet_urls(task_id, today)
    pending = await fdb.count_sheet_urls(task_id, today, status="PENDING")
    processing = await fdb.count_sheet_urls(task_id, today, status="PROCESSING")
    done = max(0, total - pending - processing)
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
    kb  = url_action_keyboard(url_obj["id"], url_obj["payment_url"], task_id=task_id)
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

    # Update status ke Google Sheet
    username = user.get("username")
    full_name = user.get("full_name")
    staff_str = f"@{username}" if username else (full_name if full_name else str(user["user_id"]))
    task = await fdb.get_task(task_id)
    tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"
    try:
        await update_sheet_status(
            payment_url,
            result.status.value,
            tab_name=tab,
            staff_info=staff_str
        )
    except Exception as e:
        logger.error(f"[SheetUpdate] Gagal update status Google Sheet untuk verify: {e}")

    # Progress tetap dicatat di Firebase untuk ditampilkan di dashboard/laporan

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

        # Update status ke Google Sheet
        username = user.get("username")
        full_name = user.get("full_name")
        staff_str = f"@{username}" if username else (full_name if full_name else str(user["user_id"]))
        task = await fdb.get_task(url_obj["task_id"])
        tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"
        try:
            await update_sheet_status(
                url_obj["payment_url"],
                "SKIPPED",
                tab_name=tab,
                staff_info=staff_str
            )
        except Exception as e:
            logger.error(f"[SheetUpdate] Gagal update status Google Sheet untuk skip: {e}")

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



async def _show_task_options_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    task: dict,
    user: dict,
    today: str,
):
    task_id = task["task_id"]
    total = await fdb.count_sheet_urls(task_id, today)
    pending = await fdb.count_sheet_urls(task_id, today, status="PENDING")
    processing = await fdb.count_sheet_urls(task_id, today, status="PROCESSING")
    done = max(0, total - pending - processing)
    bar = progress_bar(done, total)

    deadline_str = (
        task["deadline"][:16].replace("T", " ") + " WIB"
        if task.get("deadline") else "—"
    )

    text = (
        f"📋 *PILIHAN TASK*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Task     : `{task_id}`\n"
        f"📝 Judul    : {task['title']}\n"
        f"📅 Tanggal  : {today}\n"
        f"📊 Progress : {bar} ({done}/{total})\n"
        f"⏰ Deadline : {deadline_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Pilih metode verifikasi:"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ Mulai Verif (Auto)", callback_data=f"task:start_verif:{task_id}")
        ],
        [
            InlineKeyboardButton("⚡ Verif Semua PENDING", callback_data=f"url:verify_all:{task_id}:1")
        ],
        [
            InlineKeyboardButton("📋 Lihat Daftar Link", callback_data=f"url:list_page:{task_id}:1")
        ],
        [
            InlineKeyboardButton("🔙 Kembali", callback_data="menu:verif")
        ]
    ])

    msg = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await msg.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cb_task_start_verif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    task_id = update.callback_query.data.split(":")[2]
    user    = await get_or_create_user(update)
    today   = datetime.now(TZ).date().isoformat()
    await _show_next_pending_url(update, context, task_id, user["user_id"], today)


async def cb_url_list_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    parts = update.callback_query.data.split(":")
    task_id = parts[2]
    page = int(parts[3])
    today = datetime.now(TZ).date().isoformat()
    await _show_url_list(update, context, task_id, today, page)


async def _show_url_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    task_id: str,
    today: str,
    page: int,
):
    limit = 5
    offset = (page - 1) * limit
    
    # Ambil list URL untuk hari ini dan task_id
    urls, total = await fdb.list_sheet_urls(task_id=task_id, date=today, limit=limit, offset=offset)
    total_pages = max(1, (total + limit - 1) // limit)
    
    text_lines = [
        f"📋 *DAFTAR URL VERIFIKASI*",
        f"📌 Task: `{task_id}`",
        f"📅 Tanggal: {today}",
        f"━━━━━━━━━━━━━━━━━━━━"
    ]
    
    buttons = []
    
    if not urls:
        text_lines.append("📭 Tidak ada URL.")
    else:
        for idx, u in enumerate(urls, start=offset + 1):
            status = u.get("status", "PENDING")
            emoji = {
                "OK": "🟢",
                "FORMAT_ERR": "🔴",
                "DOMAIN_ERR": "🔴",
                "HTTP_ERR": "🟡",
                "TIMEOUT": "🟡",
                "PROCESSING": "⏳",
                "SKIPPED": "⏭️"
            }.get(status, "⚪")
            
            acc = u.get("account") or "-"
            notes = u.get("notes") or ""
            notes_str = f" ({notes})" if notes else ""
            
            text_lines.append(
                f"{idx}. {emoji} *{acc}*{notes_str}\n"
                f"   🔗 [Buka Stripe Checkout]({u['payment_url']})"
            )
            
            buttons.append(InlineKeyboardButton(f"⚡ Verif #{idx}", callback_data=f"url:show_detail:{u['id']}:{page}"))
            
    text_lines.append("━━━━━━━━━━━━━━━━━━━━")
    text_lines.append(f"Silakan klik link di atas untuk membuka Stripe Checkout.")
    text_lines.append(f"Klik tombol di bawah untuk memverifikasi URL spesifik.")
    
    kb_rows = []
    row = []
    for btn in buttons:
        row.append(btn)
        if len(row) == 5:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)
        
    if urls:
        kb_rows.append([InlineKeyboardButton("⚡ Verif Semua PENDING", callback_data=f"url:verify_all:{task_id}:{page}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"url:list_page:{task_id}:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"url:list_page:{task_id}:{page+1}"))
    kb_rows.append(nav_row)
    
    kb_rows.append([InlineKeyboardButton("🔙 Kembali", callback_data=f"task:select:{task_id}")])
    markup = InlineKeyboardMarkup(kb_rows)
    
    msg = update.callback_query.message
    try:
        await update.callback_query.edit_message_text(
            "\n".join(text_lines),
            parse_mode="Markdown",
            reply_markup=markup,
            disable_web_page_preview=True
        )
    except Exception:
        await msg.reply_text(
            "\n".join(text_lines),
            parse_mode="Markdown",
            reply_markup=markup,
            disable_web_page_preview=True
        )


async def cb_url_show_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    parts = update.callback_query.data.split(":")
    doc_id = parts[2]
    page = int(parts[3])
    
    url_obj = await fdb.get_sheet_url(doc_id)
    if not url_obj:
        await update.callback_query.message.reply_text("❌ URL tidak ditemukan.")
        return
        
    task_id = url_obj["task_id"]
    today = url_obj["date"]
    
    status_emoji = {
        "OK": "🟢",
        "FORMAT_ERR": "🔴",
        "DOMAIN_ERR": "🔴",
        "HTTP_ERR": "🟡",
        "TIMEOUT": "🟡",
        "PROCESSING": "⏳",
        "SKIPPED": "⏭️"
    }.get(url_obj.get("status"), "⚪")
    
    text = (
        f"🔗 *DETAIL URL VERIFIKASI*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Task     : `{task_id}`\n"
        f"📅 Tanggal  : {today}\n"
        f"👤 Akun     : {url_obj.get('account') or '-'}\n"
        f"📝 Catatan  : {url_obj.get('notes') or '-'}\n"
        f"📊 Status   : {status_emoji} {url_obj.get('status')}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 URL:\n`{url_obj['payment_url']}`\n\n"
        f"Klik *Verifikasi Sekarang* untuk memeriksa URL ini."
    )
    
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌐 Buka Link Stripe", url=url_obj["payment_url"])
        ],
        [
            InlineKeyboardButton("✅ Verifikasi Sekarang", callback_data=f"url:verify_detail:{doc_id}:{page}"),
            InlineKeyboardButton("⏭️ Skip", callback_data=f"url:skip_detail:{doc_id}:{page}"),
        ],
        [
            InlineKeyboardButton("🔙 Kembali ke List", callback_data=f"url:list_page:{task_id}:{page}")
        ]
    ])
    
    msg = update.callback_query.message
    try:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cb_url_verify_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("⏳ Memeriksa URL...")
    parts = update.callback_query.data.split(":")
    doc_id = parts[2]
    page = int(parts[3])
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

    # Update status ke Google Sheet
    username = user.get("username")
    full_name = user.get("full_name")
    staff_str = f"@{username}" if username else (full_name if full_name else str(user["user_id"]))
    task = await fdb.get_task(task_id)
    tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"
    try:
        await update_sheet_status(
            payment_url,
            result.status.value,
            tab_name=tab,
            staff_info=staff_str
        )
    except Exception as e:
        logger.error(f"[SheetUpdate] Gagal update status Google Sheet untuk verify_detail: {e}")

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
        f"Pesan  : {result.message}",
        parse_mode="Markdown",
    )
    
    await _show_url_list(update, context, task_id, today, page)


async def cb_url_skip_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("⏭️ URL dilewati")
    parts = update.callback_query.data.split(":")
    doc_id = parts[2]
    page = int(parts[3])
    user   = await get_or_create_user(update)

    url_obj = await fdb.get_sheet_url(doc_id)
    if url_obj:
        await fdb.update_sheet_url(doc_id,
            status="SKIPPED",
            verified_by=user["user_id"],
            verified_at=now_wib().isoformat(),
        )

        # Update status ke Google Sheet
        username = user.get("username")
        full_name = user.get("full_name")
        staff_str = f"@{username}" if username else (full_name if full_name else str(user["user_id"]))
        task = await fdb.get_task(url_obj["task_id"])
        tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"
        try:
            await update_sheet_status(
                url_obj["payment_url"],
                "SKIPPED",
                tab_name=tab,
                staff_info=staff_str
            )
        except Exception as e:
            logger.error(f"[SheetUpdate] Gagal update status Google Sheet untuk skip_detail: {e}")
        
        await _show_url_list(update, context, url_obj["task_id"], url_obj["date"], page)


async def cb_url_verify_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("⏳ Memverifikasi semua URL PENDING...")
    parts = update.callback_query.data.split(":")
    task_id = parts[2]
    page = int(parts[3])
    user = await get_or_create_user(update)
    today = datetime.now(TZ).date().isoformat()

    task = await fdb.get_task(task_id)
    if not task:
        await update.callback_query.message.reply_text("❌ Task tidak ditemukan.")
        return

    # Check quota per staff harian
    quota_staff = task.get("quota_per_staff", 0)
    remaining_quota = 999999
    if quota_staff > 0:
        prog = await fdb.get_progress(task_id, user["user_id"], today)
        submitted = prog.get("submitted", 0) if prog else 0
        remaining_quota = max(0, quota_staff - submitted)
        if remaining_quota <= 0:
            await update.callback_query.message.reply_text(
                f"⚠️ *Kuota Staff Terpenuhi!*\n"
                f"Anda telah memproses {submitted}/{quota_staff} URL untuk task ini hari ini.",
                parse_mode="Markdown",
                reply_markup=back_keyboard()
            )
            return

    # Ambil semua URL PENDING untuk hari ini
    pending_urls, total_pending = await fdb.list_sheet_urls(
        task_id=task_id, date=today, status="PENDING", limit=500
    )

    if not pending_urls:
        await update.callback_query.message.reply_text(
            "📭 Tidak ada URL PENDING yang perlu diverifikasi.",
            reply_markup=back_keyboard()
        )
        return

    # Batasi dengan remaining_quota
    urls_to_verify = pending_urls[:remaining_quota]
    
    # Beri tahu user bahwa proses sedang berjalan
    progress_msg = await update.callback_query.message.reply_text(
        f"⏳ Memproses verifikasi *{len(urls_to_verify)}* URL PENDING secara massal...",
        parse_mode="Markdown"
    )

    sem = asyncio.Semaphore(5)
    async def verify_and_update(url_obj):
        doc_id = url_obj["id"]
        payment_url = url_obj["payment_url"]
        
        # 1. Update ke PROCESSING agar tidak diclaim/diverif ganda
        try:
            await fdb.update_sheet_url(doc_id,
                status="PROCESSING",
                verified_by=str(user["user_id"]),
                assigned_at=now_wib().isoformat()
            )
        except Exception as e:
            logger.warning(f"Failed to mark as processing {doc_id}: {e}")
            return None
            
        async with sem:
            # 2. Verifikasi URL
            result = await verify_url(payment_url)
            
            # 3. Update status verifikasi di DB
            await fdb.update_sheet_url(doc_id,
                status=result.status.value,
                http_code=result.http_code,
                error_msg=result.message if not result.is_ok else None,
                verified_by=user["user_id"],
                verified_at=now_wib().isoformat(),
            )
            
            # 4. Update status ke Google Sheet
            username = user.get("username")
            full_name = user.get("full_name")
            staff_str = f"@{username}" if username else (full_name if full_name else str(user["user_id"]))
            tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"
            try:
                await update_sheet_status(
                    payment_url,
                    result.status.value,
                    tab_name=tab,
                    staff_info=staff_str
                )
            except Exception as e:
                logger.error(f"[SheetUpdate] Gagal update status Google Sheet untuk verify_all: {e}")
            
            # 5. Catat audit log
            await fdb.add_audit_log(
                actor_id=user["user_id"], action="url.verify",
                target_type="sheet_url", target_id=doc_id,
                detail={"url": payment_url, "status": result.status.value,
                        "http_code": result.http_code},
            )
            
            return result

    tasks_to_run = [verify_and_update(u) for u in urls_to_verify]
    results = await asyncio.gather(*tasks_to_run)
    
    valid_results = [r for r in results if r is not None]
    
    submitted_delta = len(valid_results)
    ok_delta = sum(1 for r in valid_results if r.is_ok)
    fail_delta = submitted_delta - ok_delta

    if submitted_delta > 0:
        await fdb.upsert_progress(
            task_id=task_id, user_id=user["user_id"], date=today,
            submitted_delta=submitted_delta,
            ok_delta=ok_delta,
            fail_delta=fail_delta
        )

    try:
        await progress_msg.delete()
    except Exception:
        pass

    await update.callback_query.message.reply_text(
        f"✅ *Verifikasi Massal Selesai!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 Task     : `{task_id}`\n"
        f"📊 Diproses : {submitted_delta} URL\n"
        f"🟢 Valid    : {ok_delta}\n"
        f"🔴/🟡 Gagal : {fail_delta}",
        parse_mode="Markdown"
    )

    await _show_url_list(update, context, task_id, today, page)


def get_handlers():
    return [
        CommandHandler("verif",  cmd_verif),
        CallbackQueryHandler(cb_task_select,      pattern=r"^task:select:.+$"),
        CallbackQueryHandler(cb_task_start_verif, pattern=r"^task:start_verif:.+$"),
        CallbackQueryHandler(cb_url_list_page,    pattern=r"^url:list_page:.+$"),
        CallbackQueryHandler(cb_url_show_detail,  pattern=r"^url:show_detail:.+$"),
        CallbackQueryHandler(cb_url_verify_detail, pattern=r"^url:verify_detail:.+$"),
        CallbackQueryHandler(cb_url_skip_detail,   pattern=r"^url:skip_detail:.+$"),
        CallbackQueryHandler(cb_url_verify,       pattern=r"^url:verify:.+$"),
        CallbackQueryHandler(cb_url_skip,         pattern=r"^url:skip:.+$"),
        CallbackQueryHandler(cb_url_verify_all,   pattern=r"^url:verify_all:.+$"),
        CallbackQueryHandler(cb_menu_sync_sheet,  pattern="^menu:sync_sheet$"),
    ]
