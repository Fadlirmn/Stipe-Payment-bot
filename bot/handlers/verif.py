"""
handlers/verif.py — Alur verifikasi URL dari Google Sheets (PostgreSQL version)
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
from bot.services.url_verifier import verify_url, check_leonardo_api_key, verify_stripe_and_credits, VerifResult, VerifStatus
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

    # Quota bersifat INFORMATIF — tidak memblokir akses verifikasi


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


async def _sync_sheet_to_db(task: dict, target_date: str) -> tuple[int, str | None]:
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
        row_date = row.get("date")
        if row_date and row_date != target_date:
            logger.warning(f"[Sync] Row date {row_date} does not match target_date {target_date}. Skipping.")
            continue

        # Cek status assignment dari Google Sheets
        sheet_status = row.get("status", "")
        assigned_user_id = None
        if sheet_status and sheet_status.startswith("ASSIGNED"):
            # Format: "ASSIGNED - @username"
            parts = sheet_status.split("-")
            if len(parts) > 1:
                uname = parts[1].strip()
                user_obj = await fdb.get_user_by_username(uname)
                if user_obj:
                    assigned_user_id = str(user_obj["user_id"])

        doc_id = hashlib.md5(f"{task_id}_{row['payment_url']}".encode("utf-8")).hexdigest()
        
        if existing_ids is not None and doc_id in existing_ids:
            # Jika baris sudah ada di DB, sinkronkan info assignment jika masih PENDING/PROCESSING di DB
            if assigned_user_id:
                db_url = await fdb.get_sheet_url(doc_id)
                if db_url and db_url.get("status") in ("PENDING", "PROCESSING") and db_url.get("verified_by") != assigned_user_id:
                    update_data = {
                        "status": "PROCESSING",
                        "verified_by": assigned_user_id,
                        "assigned_at": now_wib().isoformat()
                    }
                    # assigned_to hanya diisi sekali, tidak pernah ditimpa
                    if not db_url.get("assigned_to"):
                        update_data["assigned_to"] = assigned_user_id
                    await fdb.update_sheet_url(doc_id, **update_data)
            continue

        await fdb.add_sheet_url(
            task_id=task_id,
            date=target_date,
            account=row["account"],
            payment_url=row["payment_url"],
            notes=row["notes"],
            api_key=row.get("api_key", ""),
            check_exists=(existing_ids is None),
        )
        
        # Jika baru masuk dan sudah berstatus ASSIGNED di Sheets
        if assigned_user_id:
            await fdb.update_sheet_url(
                doc_id,
                status="PROCESSING",
                assigned_to=assigned_user_id,
                verified_by=assigned_user_id,
                assigned_at=now_wib().isoformat()
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
    # Quota bersifat INFORMATIF — tidak memblokir pengambilan URL berikutnya


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

        # Jalankan update secara paralel di background (non-blocking)
        asyncio.create_task(asyncio.gather(*(safe_update(u) for u in claimed_urls), return_exceptions=True))

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
    api_key     = url_obj.get("api_key", "")

    # Quota bersifat INFORMATIF — tidak memblokir verifikasi
    task = await fdb.get_task(task_id)


    result, api_key_status = await verify_stripe_and_credits(payment_url, api_key)

    username = user.get("username")
    full_name = user.get("full_name")
    staff_str = f"@{username}" if username else (full_name if full_name else str(user["user_id"]))
    task = await fdb.get_task(task_id)
    tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"

    # Selalu update status (OK/FAIL) dan selalu hitung submitted → warna 🟢/🔴 muncul di list
    db_update = {
        "status": result.status.value,
        "http_code": result.http_code,
        "error_msg": result.message if not result.is_ok else None,
        "verified_by": user["user_id"],
        "verified_at": now_wib().isoformat(),
    }
    # assigned_to hanya diisi sekali (staff asli), tidak pernah ditimpa
    if not url_obj.get("assigned_to"):
        db_update["assigned_to"] = str(user["user_id"])
    if api_key:
        db_update["api_key_status"] = api_key_status
    await fdb.update_sheet_url(doc_id, **db_update)

    async def bg_sheet():
        try:
            await update_sheet_status(payment_url, result.status.value,
                                      tab_name=tab, staff_info=staff_str)
        except Exception as e:
            logger.error(f"[SheetUpdate] Gagal update sheet auto-verif: {e}")
    asyncio.create_task(bg_sheet())

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

    api_info_str = ""
    if api_key:
        masked_api = api_key[:6] + "..." + api_key[-6:] if len(api_key) > 12 else api_key
        api_badge = f"🟢 {api_key_status}" if api_key_status and api_key_status.startswith("ACTIVE") else f"🔴 {api_key_status}"
        api_info_str = f"API Key: `{masked_api}`\nStatus API: {api_badge}\n"

    if result.is_ok:
        # ✅ Sukses — tampilkan hasil, lanjut ke URL berikutnya
        await update.callback_query.message.reply_text(
            f"{result.emoji} *Hasil Verifikasi*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Status : {status_badge(result.status.value)}\n"
            f"HTTP   : {result.http_code or '-'}\n"
            f"Pesan  : {result.message}\n"
            f"{api_info_str}"
            f"URL    : `{payment_url[:60]}...`",
            parse_mode="Markdown",
        )
        await _show_next_pending_url(update, context, task_id, user["user_id"], today)
    else:
        # ❌ Gagal — tampilkan hasil + opsi verif ulang (status sudah 🔴 di DB)
        retry_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Verif Ulang", callback_data=f"url:retry:{doc_id}:auto")],
            [InlineKeyboardButton("⏭️ URL Berikutnya", callback_data=f"task:start_verif:{task_id}")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="menu:verif")],
        ])
        await update.callback_query.message.reply_text(
            f"{result.emoji} *Hasil Verifikasi — GAGAL*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Status : {status_badge(result.status.value)}\n"
            f"HTTP   : {result.http_code or '-'}\n"
            f"Pesan  : {result.message}\n"
            f"{api_info_str}"
            f"URL    : `{payment_url[:60]}...`\n\n"
            f"⚠️ URL sudah dihitung ke progress. Ingin coba lagi?",
            parse_mode="Markdown",
            reply_markup=retry_kb,
        )


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

        # Update status ke Google Sheet (non-blocking background task)
        username = user.get("username")
        full_name = user.get("full_name")
        staff_str = f"@{username}" if username else (full_name if full_name else str(user["user_id"]))
        task = await fdb.get_task(url_obj["task_id"])
        tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"
        
        async def bg_update_skip():
            try:
                await update_sheet_status(
                    url_obj["payment_url"],
                    "SKIPPED",
                    tab_name=tab,
                    staff_info=staff_str
                )
            except Exception as e:
                logger.error(f"[SheetUpdate] Gagal update status Google Sheet untuk skip: {e}")
        asyncio.create_task(bg_update_skip())

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
        count, err = await _sync_sheet_to_db(task, today)
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

    prog = await fdb.get_progress(task_id, user["user_id"], today)
    user_done = prog.get("submitted", 0) if prog else 0
    quota_staff = task.get("quota_per_staff", 0)
    quota_staff_str = f"/{quota_staff}" if quota_staff > 0 else " (unlimited)"

    text = (
        f"📋 *PILIHAN TASK*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Task       : `{task_id}`\n"
        f"📝 Judul      : {task['title']}\n"
        f"📅 Tanggal    : {today}\n"
        f"📊 Progress   : {bar} ({done}/{total})\n"
        f"👤 Milik Saya : {user_done}{quota_staff_str}\n"
        f"⏰ Deadline   : {deadline_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Pilih metode verifikasi:"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 Ambil Link", callback_data=f"task:start_verif:{task_id}")
        ],
        [
            InlineKeyboardButton("⚡ Verif Auto", callback_data=f"url:verify_all:{task_id}:1")
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
    user = await get_or_create_user(update)
    task = await fdb.get_task(task_id)
    quota_staff = task.get("quota_per_staff", 0) if task else 0

    # Cek quota — tapi JANGAN blokir akses list, cukup tandai agar tombol verif disembunyikan
    quota_exceeded = False
    submitted = 0
    if quota_staff > 0 and user.get("role") not in ("admin", "dev"):
        prog = await fdb.get_progress(task_id, user["user_id"], today)
        submitted = prog.get("submitted", 0) if prog else 0
        quota_exceeded = submitted >= quota_staff

    limit = 5
    offset = (page - 1) * limit

    # Sync quota dulu — pastikan reserved block sesuai quota terbaru dari DB
    verified_by_filter = None
    if user.get("role") not in ("admin", "dev"):
        if quota_staff > 0:
            verified_by_filter = str(user["user_id"])
        if not quota_exceeded:
            newly_assigned = await fdb.ensure_quota_synced(task_id, today, user["user_id"])
            if newly_assigned:
                # Update Sheets untuk URL yang baru di-assign
                user_data = await fdb.get_user(user["user_id"])
                username  = user_data.get("username") if user_data else None
                full_name = user_data.get("full_name") if user_data else None
                staff_str = f"@{username}" if username else (full_name if full_name else str(user["user_id"]))
                status_str = f"ASSIGNED - {staff_str}"
                tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"

                sem_assign = asyncio.Semaphore(5)
                async def _sheet_assign(u):
                    async with sem_assign:
                        try:
                            await update_sheet_status(
                                u["payment_url"], status_str,
                                tab_name=tab, staff_info=staff_str
                            )
                        except Exception as e:
                            logger.warning(f"[SheetAssign] Gagal update Sheets assign: {e}")
                asyncio.create_task(
                    asyncio.gather(*(_sheet_assign(u) for u in newly_assigned), return_exceptions=True)
                )

    urls, total = await fdb.list_sheet_urls(
        task_id=task_id, date=today, limit=limit, offset=offset,
        verified_by=verified_by_filter
    )
    total_pages = max(1, (total + limit - 1) // limit)

    quota_str = f"{submitted}/{quota_staff}" if quota_staff > 0 else f"{submitted} (unlimited)"
    text_lines = [
        f"📋 *DAFTAR URL VERIFIKASI*",
        f"📌 Task   : `{task_id}`",
        f"📅 Tanggal: {today}",
        f"👤 Kuota  : {quota_str}",
        f"━━━━━━━━━━━━━━━━━━━━",
    ]
    if quota_exceeded:
        text_lines.append("✅ *Kuota hari ini sudah terpenuhi* — Anda bisa melihat link tapi verifikasi ditutup.")
        text_lines.append("━━━━━━━━━━━━━━━━━━━━")

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

            staff_str = ""
            verified_by_id = u.get("verified_by")
            if verified_by_id:
                try:
                    staff_user = await fdb.get_user(int(verified_by_id))
                    if staff_user:
                        staff_name = staff_user.get("full_name") or staff_user.get("username") or verified_by_id
                        staff_str = f" | 👤 {staff_name}"
                except Exception:
                    pass

            text_lines.append(
                f"{idx}. {emoji} *{acc}*{notes_str}{staff_str}\n"
                f"   🔗 [Buka Stripe Checkout]({u['payment_url']})"
            )

            # Tombol verif hanya tampil jika quota belum penuh
            if not quota_exceeded:
                buttons.append(InlineKeyboardButton(
                    f"⚡ Verif #{idx}", callback_data=f"url:show_detail:{u['id']}:{page}"
                ))

    text_lines.append("━━━━━━━━━━━━━━━━━━━━")
    if quota_exceeded:
        text_lines.append("_Link di atas bisa dibuka langsung dari Telegram._")
    else:
        text_lines.append("Klik link untuk membuka Stripe Checkout, atau tombol untuk verifikasi.")

    kb_rows = []
    row = []
    for btn in buttons:
        row.append(btn)
        if len(row) == 5:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)

    # Selalu tampilkan tombol "⚡ Verif Auto" agar staff bisa klik dan melihat status link aktif & link semuanya
    if urls:
        kb_rows.append([InlineKeyboardButton(
            "⚡ Verif Auto", callback_data=f"url:verify_all:{task_id}:{page}"
        )])

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
    user = await get_or_create_user(update)
    
    task = await fdb.get_task(task_id)
    quota_staff = task.get("quota_per_staff", 0) if task else 0
    quota_exceeded = False
    submitted = 0
    if quota_staff > 0 and user.get("role") not in ("admin", "dev"):
        prog = await fdb.get_progress(task_id, user["user_id"], today)
        submitted = prog.get("submitted", 0) if prog else 0
        if submitted >= quota_staff:
            quota_exceeded = True
    
    status_emoji = {
        "OK": "🟢",
        "FORMAT_ERR": "🔴",
        "DOMAIN_ERR": "🔴",
        "HTTP_ERR": "🟡",
        "TIMEOUT": "🟡",
        "PROCESSING": "⏳",
        "SKIPPED": "⏭️"
    }.get(url_obj.get("status"), "⚪")
    
    staff_name = "-"
    verified_by_id = url_obj.get("verified_by")
    if verified_by_id:
        try:
            staff_user = await fdb.get_user(int(verified_by_id))
            if staff_user:
                staff_name = staff_user.get("full_name") or staff_user.get("username") or verified_by_id
        except Exception:
            pass

    text = (
        f"🔗 *DETAIL URL VERIFIKASI*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Task     : `{task_id}`\n"
        f"📅 Tanggal  : {today}\n"
        f"👤 Akun     : {url_obj.get('account') or '-'}\n"
        f"📝 Catatan  : {url_obj.get('notes') or '-'}\n"
        f"👤 Staff    : {staff_name}\n"
        f"📊 Status   : {status_emoji} {url_obj.get('status')}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 URL:\n`{url_obj['payment_url']}`\n\n"
    )
    
    if quota_exceeded:
        text += f"⚠️ *Kuota Staff Terpenuhi!*\nAnda telah memproses {submitted}/{quota_staff} URL untuk task ini hari ini."
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🌐 Buka Link Stripe", url=url_obj["payment_url"])
            ],
            [
                InlineKeyboardButton("🔙 Kembali ke List", callback_data=f"url:list_page:{task_id}:{page}")
            ]
        ])
    else:
        text += f"Klik *Verifikasi Sekarang* untuk memeriksa URL ini."
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
    api_key     = url_obj.get("api_key", "")

    # Quota bersifat INFORMATIF — tidak memblokir verifikasi
    task = await fdb.get_task(task_id)


    result, api_key_status = await verify_stripe_and_credits(payment_url, api_key)

    # Selalu update status + hitung submitted → warna 🟢/🔴 di list tetap muncul
    db_update = {
        "status": result.status.value,
        "http_code": result.http_code,
        "error_msg": result.message if not result.is_ok else None,
        "verified_by": user["user_id"],
        "verified_at": now_wib().isoformat(),
    }
    if api_key:
        db_update["api_key_status"] = api_key_status
    await fdb.update_sheet_url(doc_id, **db_update)

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

    api_info_str = ""
    if api_key:
        masked_api = api_key[:6] + "..." + api_key[-6:] if len(api_key) > 12 else api_key
        api_badge = f"🟢 {api_key_status}" if api_key_status and api_key_status.startswith("ACTIVE") else f"🔴 {api_key_status}"
        api_info_str = f"API Key: `{masked_api}`\nStatus API: {api_badge}\n"

    if result.is_ok:
        # ✅ Sukses — tampilkan hasil, kembali ke list
        await update.callback_query.message.reply_text(
            f"{result.emoji} *Hasil Verifikasi*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Status : {status_badge(result.status.value)}\n"
            f"HTTP   : {result.http_code or '-'}\n"
            f"Pesan  : {result.message}\n"
            f"{api_info_str}",
            parse_mode="Markdown",
        )
        await _show_url_list(update, context, task_id, today, page)
    else:
        # ❌ Gagal — status 🔴 sudah tersimpan, tampilkan hasil + opsi verif ulang
        retry_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Verif Ulang", callback_data=f"url:retry:{doc_id}:list:{page}")],
            [InlineKeyboardButton("📋 Kembali ke List", callback_data=f"url:list_page:{task_id}:{page}")],
        ])
        await update.callback_query.message.reply_text(
            f"{result.emoji} *Hasil Verifikasi — GAGAL*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Status : {status_badge(result.status.value)}\n"
            f"HTTP   : {result.http_code or '-'}\n"
            f"Pesan  : {result.message}\n"
            f"{api_info_str}"
            f"URL    : `{payment_url[:60]}...`\n\n"
            f"⚠️ Sudah dihitung ke progress. Ingin coba verifikasi ulang?",
            parse_mode="Markdown",
            reply_markup=retry_kb,
        )


async def cb_url_skip_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("⏭️ URL dilewati")
    parts = update.callback_query.data.split(":")
    doc_id = parts[2]
    page = int(parts[3])
    user   = await get_or_create_user(update)

    url_obj = await fdb.get_sheet_url(doc_id)
    if url_obj:
        # Check quota per staff harian
        task = await fdb.get_task(url_obj["task_id"])
        quota_staff = task.get("quota_per_staff", 0) if task else 0
        if quota_staff > 0:
            prog = await fdb.get_progress(url_obj["task_id"], user["user_id"], url_obj["date"])
            submitted = prog.get("submitted", 0) if prog else 0
            if submitted >= quota_staff:
                await update.callback_query.message.reply_text(
                    f"⚠️ *Kuota Staff Terpenuhi!*\n"
                    f"Anda telah memproses {submitted}/{quota_staff} URL untuk task ini hari ini.",
                    parse_mode="Markdown",
                    reply_markup=back_keyboard()
                )
                return

        await fdb.update_sheet_url(doc_id,
            status="SKIPPED",
            verified_by=user["user_id"],
            verified_at=now_wib().isoformat(),
        )
        
        await _show_url_list(update, context, url_obj["task_id"], url_obj["date"], page)


async def cb_url_verify_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
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
    submitted = 0
    remaining_quota = 999999
    if quota_staff > 0:
        prog = await fdb.get_progress(task_id, user["user_id"], today)
        submitted = prog.get("submitted", 0) if prog else 0
        remaining_quota = max(0, quota_staff - submitted)

    # Ambil link status counts
    ok_count = await fdb.count_sheet_urls(task_id, today, status="OK")
    total_count = await fdb.count_sheet_urls(task_id, today)

    # Staff SELALU hanya melihat URL miliknya sendiri
    verified_by_filter = None
    if user.get("role") not in ("admin", "dev"):
        verified_by_filter = str(user["user_id"])
    
    pending_urls, _ = await fdb.list_sheet_urls(
        task_id=task_id, date=today, status="PENDING", limit=500, verified_by=verified_by_filter
    )
    processing_urls, _ = await fdb.list_sheet_urls(
        task_id=task_id, date=today, status="PROCESSING", limit=500, verified_by=verified_by_filter
    )
    urls_to_verify_all = processing_urls + pending_urls
    pending_count = len(urls_to_verify_all)

    # Buat progress bar untuk kontribusi staff harian
    quota_str = f"/{quota_staff}" if quota_staff > 0 else " (unlimited)"
    contrib_progress = f"{submitted}{quota_str}"
    if quota_staff > 0:
        bar = progress_bar(submitted, quota_staff)
        contrib_progress = f"{bar} ({submitted}/{quota_staff})"

    text = (
        f"📋 *STATUS VERIFIKASI TASK*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Task       : `{task_id}`\n"
        f"📅 Tanggal    : {today}\n"
        f"🟢 Link Aktif : {ok_count} URL\n"
        f"📊 Link Semua : {total_count} URL\n"
        f"👤 Kontribusi : {contrib_progress}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *Tanggung Jawab Staff:*\n"
        f"_Verifikasi massal memproses semua URL PENDING otomatis. Pastikan Anda tetap memantau validitas link jika ada kendala._\n"
    )

    kb_rows = []
    # Jika kuota penuh (remaining_quota <= 0) ATAU tidak ada pending, tidak bisa/perlu verif massal
    if remaining_quota <= 0:
        kb_rows.append([InlineKeyboardButton("🔙 Kembali ke List", callback_data=f"url:list_page:{task_id}:{page}")])
    elif pending_count == 0:
        text += f"\n📭 _Tidak ada URL PENDING atau PROCESSING yang perlu diverifikasi._"
        kb_rows.append([InlineKeyboardButton("🔙 Kembali ke List", callback_data=f"url:list_page:{task_id}:{page}")])
    else:
        text += f"\nApakah Anda yakin ingin memproses *{min(pending_count, remaining_quota)}* URL secara otomatis?"
        kb_rows.append([
            InlineKeyboardButton("✅ Ya, Jalankan Verifikasi", callback_data=f"url:verify_confirm:{task_id}:{page}"),
            InlineKeyboardButton("❌ Batal", callback_data=f"url:list_page:{task_id}:{page}")
        ])

    markup = InlineKeyboardMarkup(kb_rows)
    msg = update.callback_query.message
    try:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def cb_url_verify_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("⏳ Memulai verifikasi massal...")
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
            await _show_url_list(update, context, task_id, today, page)
            return

    # Staff SELALU hanya verif URL miliknya sendiri
    verified_by_filter = None
    if user.get("role") not in ("admin", "dev"):
        verified_by_filter = str(user["user_id"])
    
    pending_urls, _ = await fdb.list_sheet_urls(
        task_id=task_id, date=today, status="PENDING", limit=500, verified_by=verified_by_filter
    )
    processing_urls, _ = await fdb.list_sheet_urls(
        task_id=task_id, date=today, status="PROCESSING", limit=500, verified_by=verified_by_filter
    )
    
    urls_to_verify_all = processing_urls + pending_urls

    if not urls_to_verify_all:
        await _show_url_list(update, context, task_id, today, page)
        return

    # Batasi dengan remaining_quota
    urls_to_verify = urls_to_verify_all[:remaining_quota]
    total_to_verify = len(urls_to_verify)
    
    # Beri tahu user bahwa proses sedang berjalan
    progress_msg = await update.callback_query.message.reply_text(
        f"⏳ *Memproses verifikasi... (0/{total_to_verify})*\n"
        f"Mohon tunggu sebentar, sedang memvalidasi link...",
        parse_mode="Markdown"
    )

    processed_count = 0
    last_edit_time = 0
    progress_lock = asyncio.Lock()

    async def update_progress_cb():
        nonlocal last_edit_time
        import time
        now = time.time()
        # Throttling to prevent Telegram API rate limiting (min 1.5s interval or final edit)
        if now - last_edit_time > 1.5 or processed_count == total_to_verify:
            last_edit_time = now
            try:
                anim_emoji = ["⏳", "🔍", "⚡", "🔄"][processed_count % 4]
                await progress_msg.edit_text(
                    f"{anim_emoji} *Memproses verifikasi... ({processed_count}/{total_to_verify})*\n"
                    f"Mohon tunggu sebentar, sedang memvalidasi link...",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    sem = asyncio.Semaphore(5)

    async def verify_and_update(url_obj):
        nonlocal processed_count
        async with sem:
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
            async with progress_lock:
                processed_count += 1
                await update_progress_cb()
            return None
            
        # 2. Verifikasi URL / API Key
        api_key = url_obj.get("api_key", "")
        result, api_key_status = await verify_stripe_and_credits(payment_url, api_key)
            
        # 3. Update status verifikasi di DB
        db_update = {
            "status": result.status.value,
            "http_code": result.http_code,
            "error_msg": result.message if not result.is_ok else None,
            "verified_by": user["user_id"],
            "verified_at": now_wib().isoformat(),
        }
        # assigned_to hanya diisi sekali (staff asli)
        current_url = await fdb.get_sheet_url(doc_id)
        if current_url and not current_url.get("assigned_to"):
            db_update["assigned_to"] = str(user["user_id"])
        if api_key:
            db_update["api_key_status"] = api_key_status
        await fdb.update_sheet_url(doc_id, **db_update)
        
        # 4. Catat audit log
        await fdb.add_audit_log(
            actor_id=user["user_id"], action="url.verify",
            target_type="sheet_url", target_id=doc_id,
            detail={"url": payment_url, "status": result.status.value,
                    "http_code": result.http_code},
        )
        
        # 5. Update status ke Google Sheet (non-blocking background task)
        staff_str = f"@{user.get('username')}" if user.get('username') else (user.get('full_name') if user.get('full_name') else str(user["user_id"]))
        tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"
        async def bg_update_sheet_bulk():
            try:
                await update_sheet_status(
                    payment_url,
                    result.status.value,
                    tab_name=tab,
                    staff_info=staff_str
                )
            except Exception as e:
                logger.error(f"[SheetUpdate] Gagal update status Google Sheet untuk verify_all: {e}")
        asyncio.create_task(bg_update_sheet_bulk())
        
        async with progress_lock:
            processed_count += 1
            await update_progress_cb()
            
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



async def cb_url_retry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset URL gagal kembali ke PROCESSING untuk verif ulang."""
    await update.callback_query.answer("🔄 Menyiapkan verifikasi ulang...")
    parts = update.callback_query.data.split(":")
    # Format baru: url:retry:{doc_id}:{flow}  atau  url:retry:{doc_id}:{flow}:{page}
    doc_id = parts[2]
    flow   = parts[3] if len(parts) > 3 else "auto"
    page   = int(parts[4]) if len(parts) > 4 else 1

    user = await get_or_create_user(update)
    today = datetime.now(TZ).date().isoformat()

    url_obj = await fdb.get_sheet_url(doc_id)
    if not url_obj:
        await update.callback_query.message.reply_text("❌ URL tidak ditemukan.")
        return

    task_id = url_obj["task_id"]

    # Reset status kembali ke PROCESSING agar bisa diverif ulang
    # Kurangi fail_delta & submitted_delta yang sudah dihitung sebelumnya
    await fdb.update_sheet_url(doc_id, status="PROCESSING", error_msg=None)
    await fdb.upsert_progress(
        task_id=task_id, user_id=user["user_id"], date=today,
        submitted_delta=-1, ok_delta=0, fail_delta=-1,
    )

    if flow == "auto":
        await _show_next_pending_url(update, context, task_id, user["user_id"], today)
    else:
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
        CallbackQueryHandler(cb_url_retry,         pattern=r"^url:retry:.+$"),
        CallbackQueryHandler(cb_url_verify,        pattern=r"^url:verify:.+$"),
        CallbackQueryHandler(cb_url_skip,          pattern=r"^url:skip:.+$"),
        CallbackQueryHandler(cb_url_verify_all_confirm, pattern=r"^url:verify_confirm:.+$"),
        CallbackQueryHandler(cb_url_verify_all,    pattern=r"^url:verify_all:.+$"),
        CallbackQueryHandler(cb_menu_sync_sheet,   pattern="^menu:sync_sheet$"),
    ]
