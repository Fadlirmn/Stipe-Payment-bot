"""
handlers/admin.py — Admin/Dev commands (PostgreSQL version)
"""
from __future__ import annotations

from datetime import datetime
import asyncio
from loguru import logger

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)

import bot.db as fdb
from bot.middlewares.auth import get_or_create_user, require_role
from bot.utils.keyboards import back_keyboard
from bot.utils.formatters import role_badge, progress_bar, now_wib
from bot.config import TZ, DEV_IDS, DASHBOARD_URL

(CT_TITLE, CT_DESC, CT_TAB, CT_QUOTA_TOTAL, CT_QUOTA_STAFF, CT_DEADLINE, CT_REPEAT) = range(7)

# Edit task conversation states
(ET_FIELD, ET_VALUE) = range(7, 9)


@require_role("admin", "dev")
async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Penggunaan: `/approve <user_id>`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID harus berupa angka.")
        return

    actor  = await get_or_create_user(update)
    target = await fdb.get_user(target_id)
    if not target:
        await update.message.reply_text("❌ User tidak ditemukan.")
        return

    await fdb.update_user(target_id, role="staff", approved_by=actor["user_id"])
    await fdb.add_audit_log(actor["user_id"], "user.approve", "user", str(target_id),
                             {"new_role": "staff"})

    await update.message.reply_text(
        f"✅ User `{target_id}` ({target.get('full_name')}) disetujui sebagai *Staff*.",
        parse_mode="Markdown",
    )
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text="🎉 *Selamat!* Akun Anda telah disetujui.\nKetik /menu untuk mulai.",
            parse_mode="Markdown",
        )
    except Exception:
        pass


@require_role("admin", "dev")
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Penggunaan: `/unban <user_id>`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID harus berupa angka.")
        return

    actor  = await get_or_create_user(update)
    target = await fdb.get_user(target_id)
    if not target:
        await update.message.reply_text("❌ User tidak ditemukan.")
        return

    # Aktifkan kembali & pastikan role-nya bukan pending
    new_role = target.get("role")
    if new_role in ("pending", None):
        new_role = "staff"
    await fdb.update_user(target_id, is_active=True, role=new_role)
    await fdb.add_audit_log(actor["user_id"], "user.unban", "user", str(target_id),
                             {"restored_role": new_role})

    await update.message.reply_text(
        f"✅ User `{target_id}` ({target.get('full_name')}) telah di-*unban* dan kembali aktif sebagai {role_badge(new_role)}.",
        parse_mode="Markdown",
    )
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                "✅ *Akun kamu telah diaktifkan kembali!*\n"
                "Kamu sudah bisa menggunakan bot lagi.\n"
                "Ketik /menu untuk memulai."
            ),
            parse_mode="Markdown",
        )
    except Exception:
        pass


@require_role("dev")
async def cmd_setrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Penggunaan: `/setrole <user_id> <dev|admin|staff>`", parse_mode="Markdown"
        )
        return
    try:
        target_id = int(args[0])
        new_role  = args[1].lower()
    except ValueError:
        await update.message.reply_text("❌ Format salah.")
        return

    if new_role not in ("dev", "admin", "staff"):
        await update.message.reply_text("❌ Role harus: dev | admin | staff")
        return

    actor  = await get_or_create_user(update)
    target = await fdb.get_user(target_id)
    if not target:
        await update.message.reply_text("❌ User tidak ditemukan.")
        return

    old_role = target.get("role")
    await fdb.update_user(target_id, role=new_role)
    await fdb.add_audit_log(actor["user_id"], "user.setrole", "user", str(target_id),
                             {"old_role": old_role, "new_role": new_role})

    await update.message.reply_text(
        f"✅ Role `{target_id}` diubah: {role_badge(old_role)} → {role_badge(new_role)}",
        parse_mode="Markdown",
    )


@require_role("dev")
async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await fdb.list_users()
    lines = ["👥 *DAFTAR USER*\n━━━━━━━━━━━━━━━━━━━━"]
    for u in users:
        lines.append(
            f"\n`{u['user_id']}` — {u.get('full_name') or 'N/A'}\n"
            f"   @{u.get('username') or '-'} • {role_badge(u.get('role',''))}"
            + (" • ⛔" if not u.get("is_active", True) else "")
        )
    await update.effective_message.reply_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=back_keyboard()
    )


@require_role("admin", "dev")
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(TZ).date().isoformat()
    tasks = await fdb.list_tasks()

    total, ok, fail, pending = 0, 0, 0, 0
    for task in tasks:
        t   = await fdb.count_sheet_urls(task["task_id"], today)
        o   = await fdb.count_sheet_urls(task["task_id"], today, status="OK")
        p   = await fdb.count_sheet_urls(task["task_id"], today, status="PENDING")
        total   += t
        ok      += o
        pending += p
        fail    += t - o - p

    progs = await fdb.list_progress_by_date(today)
    # Group by user
    by_user: dict[int, dict] = {}
    for p in progs:
        uid = p["user_id"]
        if uid not in by_user:
            by_user[uid] = {"submitted": 0, "ok": 0, "fail": 0}
        by_user[uid]["submitted"] += p["submitted"]
        by_user[uid]["ok"]        += p["verified_ok"]
        by_user[uid]["fail"]      += p["verified_fail"]

    bar  = progress_bar(ok + fail, total) if total else "—"
    text = (
        f"📈 *LAPORAN HARIAN — {today}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Total URL   : {total}\n"
        f"✅ OK        : {ok}\n"
        f"❌ Gagal     : {fail}\n"
        f"⚪ Pending   : {pending}\n"
        f"Progress     : {bar}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 *Per Staff:*\n"
    )
    for i, (uid, stat) in enumerate(
        sorted(by_user.items(), key=lambda x: x[1]["ok"], reverse=True), 1
    ):
        user = await fdb.get_user(uid)
        name = user.get("full_name", str(uid)) if user else str(uid)
        text += f"  {i}. {name}: {stat['ok']}✅ {stat['fail']}❌ ({stat['submitted']} total)\n"

    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=back_keyboard())



@require_role("dev")
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Penggunaan: `/broadcast <pesan>`", parse_mode="Markdown")
        return
    msg_text = " ".join(context.args)
    users    = await fdb.list_users()
    sent, failed = 0, 0
    for u in users:
        if u.get("role") == "pending" or not u.get("is_active", True):
            continue
        try:
            await context.bot.send_message(
                chat_id=u["user_id"],
                text=f"📢 *Broadcast*\n\n{msg_text}",
                parse_mode="Markdown",
            )
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"✅ Broadcast selesai.\n✔️ Terkirim: {sent} | ❌ Gagal: {failed}"
    )


# ── Config Task Wizard ────────────────────────────────────
@require_role("admin", "dev")
async def cmd_config_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "⚙️ *CONFIG TASK BARU*\n━━━━━━━━━━━━━━━━━━━━\n"
        "Langkah 1/7: Masukkan *judul task*:",
        parse_mode="Markdown",
        reply_markup=back_keyboard("menu:main"),
    )
    return CT_TITLE


async def ct_get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ct_title"] = update.message.text.strip()
    await update.message.reply_text("Langkah 2/7: *Deskripsi task* (atau `-` untuk skip):", parse_mode="Markdown")
    return CT_DESC


async def ct_get_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ct_desc"] = update.message.text.strip()
    await update.message.reply_text("Langkah 3/7: Nama *tab Google Sheet* (default: `Sheet1`):", parse_mode="Markdown")
    return CT_TAB


async def ct_get_tab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    context.user_data["ct_tab"] = val if val != "-" else "Sheet1"
    await update.message.reply_text("Langkah 4/7: *Kuota total URL* (angka, 0 = unlimited):", parse_mode="Markdown")
    return CT_QUOTA_TOTAL


async def ct_get_quota_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["ct_quota_total"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Masukkan angka.")
        return CT_QUOTA_TOTAL
    await update.message.reply_text("Langkah 5/7: *Kuota per staff* (0 = unlimited):", parse_mode="Markdown")
    return CT_QUOTA_STAFF


async def ct_get_quota_staff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["ct_quota_staff"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Masukkan angka.")
        return CT_QUOTA_STAFF
    await update.message.reply_text(
        "Langkah 6/7: *Deadline* (format: `HH:MM`) atau `-`:", parse_mode="Markdown"
    )
    return CT_DEADLINE


async def ct_get_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    if val != "-":
        try:
            today = datetime.now(TZ).date()
            hhmm  = datetime.strptime(val, "%H:%M").time()
            context.user_data["ct_deadline"] = datetime.combine(today, hhmm).replace(tzinfo=TZ).isoformat()
        except ValueError:
            await update.message.reply_text("❌ Format salah. Gunakan HH:MM.")
            return CT_DEADLINE
    else:
        context.user_data["ct_deadline"] = None
    await update.message.reply_text(
        "Langkah 7/7: *Repeat type*\nKetik: `daily` | `weekly` | `once`",
        parse_mode="Markdown",
    )
    return CT_REPEAT


async def ct_get_repeat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip().lower()
    if val not in ("daily", "weekly", "once"):
        await update.message.reply_text("❌ Pilih: daily | weekly | once")
        return CT_REPEAT

    actor   = await get_or_create_user(update)
    today   = datetime.now(TZ)
    task_id = f"TASK-{today.strftime('%Y%m%d')}-{actor['user_id']}"

    task_data = {
        "task_id":         task_id,
        "title":           context.user_data["ct_title"],
        "description":     context.user_data.get("ct_desc"),
        "sheet_tab":       context.user_data.get("ct_tab", "Sheet1"),
        "quota_total":     context.user_data.get("ct_quota_total", 0),
        "quota_per_staff": context.user_data.get("ct_quota_staff", 0),
        "deadline":        context.user_data.get("ct_deadline"),
        "repeat_type":     val,
        "status":          "active",
        "created_by":      actor["user_id"],
    }
    await fdb.create_task(task_data)
    await fdb.add_audit_log(actor["user_id"], "task.create", "task", task_id,
                             {"title": task_data["title"]})

    # Cek overlapping daily tasks
    active_tasks = await fdb.list_tasks(status="active")
    daily_active = [t for t in active_tasks if t.get("repeat_type") == "daily"]
    warning_note = ""
    if len(daily_active) >= 2:
        warning_note = (
            "⚠️ *Peringatan Dev/Admin:*\n"
            f"Terdapat *{len(daily_active)} task daily* aktif yang berjalan bersamaan hari ini.\n"
            "Hal ini berisiko menumpuk jadwal/beban kerja harian staff. Pastikan ini disengaja.\n\n"
        )

    await update.message.reply_text(
        f"✅ *Task berhasil dibuat!*\n\n"
        f"ID    : `{task_id}`\n"
        f"Judul : {task_data['title']}\n"
        f"Tab   : {task_data['sheet_tab']}\n"
        f"Repeat: {val}\n\n"
        f"{warning_note}"
        f"Staff dapat memulai verifikasi dengan /verif",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def ct_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Config task dibatalkan.", reply_markup=back_keyboard())
    return ConversationHandler.END


# ── Task Management ──────────────────────────────────────
@require_role("admin", "dev")
async def cmd_list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan daftar semua task dengan tombol aksi."""
    tasks = await fdb.list_tasks(status=None)  # semua status
    if not tasks:
        await update.effective_message.reply_text(
            "📭 Belum ada task.", reply_markup=back_keyboard()
        )
        return

    lines = ["📋 *MANAGE TASKS*\n━━━━━━━━━━━━━━━━━━━━"]
    buttons = []
    for t in tasks:
        status_icon = "🟢" if t["status"] == "active" else "🔴" if t["status"] == "paused" else "⚫"
        lines.append(f"\n{status_icon} `{t['task_id']}`\n   {t['title'][:40]}")
        buttons.append([
            InlineKeyboardButton(
                f"{status_icon} {t['title'][:28]}",
                callback_data=f"task:detail:{t['task_id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("➕ Buat Task Baru", callback_data="menu:config_task"),
    ])
    buttons.append([InlineKeyboardButton("🔙 Kembali", callback_data="menu:main")])

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def cb_task_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan detail task + tombol edit/pause/delete."""
    await update.callback_query.answer()
    task_id = update.callback_query.data.split(":", 2)[2]
    await _show_task_detail_menu(update, context, task_id)


async def _show_task_detail_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str):
    task = await fdb.get_task(task_id)
    if not task:
        await update.callback_query.message.reply_text("❌ Task tidak ditemukan.")
        return

    today = datetime.now(TZ).date().isoformat()
    total = await fdb.count_sheet_urls(task_id, today)
    done  = await fdb.count_sheet_urls(task_id, today, status="OK")
    status_icon = "🟢 Aktif" if task["status"] == "active" else "🔴 Paused" if task["status"] == "paused" else "⚫ Selesai"

    text = (
        f"📌 *DETAIL TASK*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"ID       : `{task['task_id']}`\n"
        f"Judul    : {task['title']}\n"
        f"Deskripsi: {task.get('description') or '—'}\n"
        f"Sheet Tab: {task.get('sheet_tab') or '—'}\n"
        f"Quota    : {task.get('quota_total', 0)} total / {task.get('quota_per_staff', 0)} per staff\n"
        f"Deadline : {(task.get('deadline') or '—')[:16].replace('T',' ')}\n"
        f"Repeat   : {task.get('repeat_type', '—')}\n"
        f"Status   : {status_icon}\n"
        f"Progress : {done}/{total} URL hari ini"
    )

    pause_label = "⏸️ Pause" if task["status"] == "active" else "▶️ Aktifkan"
    pause_cb    = f"task:pause:{task_id}" if task["status"] == "active" else f"task:activate:{task_id}"

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Edit", callback_data=f"task:edit:{task_id}"),
            InlineKeyboardButton(pause_label, callback_data=pause_cb),
        ],
        [
            InlineKeyboardButton("🔄 Sync Sheet", callback_data=f"task:sync:{task_id}"),
            InlineKeyboardButton("🗑️ Hapus Task", callback_data=f"task:delete_confirm:{task_id}"),
        ],
        [InlineKeyboardButton("🔙 Daftar Task", callback_data="menu:manage_tasks")],
    ])
    await update.callback_query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cb_task_sync_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    task_id = update.callback_query.data.split(":", 2)[2]
    task = await fdb.get_task(task_id)
    if not task:
        await update.callback_query.message.reply_text("❌ Task tidak ditemukan.")
        return

    msg_status = await update.callback_query.message.reply_text(
        f"⏳ Sedang sinkronisasi spreadsheet untuk task `{task['title']}`...",
        parse_mode="Markdown"
    )

    from bot.handlers.verif import _sync_sheet_to_db
    today = datetime.now(TZ).date().isoformat()
    count, err = await _sync_sheet_to_db(task, today)

    if err:
        await msg_status.edit_text(
            f"❌ *Gagal mengambil URL dari Sheet:*\n`{err}`\n\n"
            f"Pastikan APPS_SCRIPT_URL di .env sudah benar dan dideploy.",
            parse_mode="Markdown"
        )
    else:
        await msg_status.edit_text(
            f"✅ *Sinkronisasi Selesai!*\n"
            f"Berhasil menarik *{count}* URL baru dari Google Sheets.",
            parse_mode="Markdown"
        )

    # Tampilkan kembali detail task yang ter-update
    await _show_task_detail_menu(update, context, task_id)


async def cb_task_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    task_id = update.callback_query.data.split(":", 2)[2]
    actor = await get_or_create_user(update)
    await fdb.update_task(task_id, status="paused")
    await fdb.add_audit_log(actor["user_id"], "task.pause", "task", task_id, {})
    await update.callback_query.message.reply_text(
        f"⏸️ Task `{task_id}` dijeda.",
        parse_mode="Markdown",
        reply_markup=back_keyboard("menu:manage_tasks")
    )


async def cb_task_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    task_id = update.callback_query.data.split(":", 2)[2]
    actor = await get_or_create_user(update)
    await fdb.update_task(task_id, status="active")
    await fdb.add_audit_log(actor["user_id"], "task.activate", "task", task_id, {})
    # Cek overlapping daily tasks
    active_tasks = await fdb.list_tasks(status="active")
    daily_active = [t for t in active_tasks if t.get("repeat_type") == "daily"]
    warning_note = ""
    if len(daily_active) >= 2:
        warning_note = (
            "\n⚠️ *Peringatan Dev/Admin:*\n"
            f"Terdapat *{len(daily_active)} task daily* aktif yang berjalan bersamaan hari ini.\n"
            "Hal ini berisiko menumpuk jadwal/beban kerja harian staff. Pastikan ini disengaja.\n"
        )

    await update.callback_query.message.reply_text(
        f"▶️ Task `{task_id}` diaktifkan kembali.{warning_note}",
        parse_mode="Markdown",
        reply_markup=back_keyboard("menu:manage_tasks")
    )


async def cb_task_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    task_id = update.callback_query.data.split(":", 2)[2]
    context.user_data["delete_task_id"] = task_id
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Ya, Hapus!", callback_data=f"task:delete_do:{task_id}"),
        InlineKeyboardButton("❌ Batal", callback_data=f"task:detail:{task_id}"),
    ]])
    await update.callback_query.message.reply_text(
        f"⚠️ *Yakin ingin menghapus task* `{task_id}`?\n"
        "Data URL yang terkait task ini *tidak* akan dihapus.",
        parse_mode="Markdown",
        reply_markup=kb
    )


async def cb_task_delete_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    task_id = update.callback_query.data.split(":", 2)[2]
    actor = await get_or_create_user(update)
    await fdb.update_task(task_id, status="deleted")
    await fdb.add_audit_log(actor["user_id"], "task.delete", "task", task_id, {})
    await update.callback_query.message.reply_text(
        f"🗑️ Task `{task_id}` telah dihapus (status: deleted).",
        parse_mode="Markdown",
        reply_markup=back_keyboard("menu:manage_tasks")
    )


async def cb_task_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mulai flow edit task — pilih field yang ingin diubah."""
    await update.callback_query.answer()
    task_id = update.callback_query.data.split(":", 2)[2]
    context.user_data["edit_task_id"] = task_id

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Judul",       callback_data="taskedit:title"),
         InlineKeyboardButton("📄 Deskripsi",   callback_data="taskedit:description")],
        [InlineKeyboardButton("📊 Sheet Tab",   callback_data="taskedit:sheet_tab"),
         InlineKeyboardButton("🔁 Repeat Type", callback_data="taskedit:repeat_type")],
        [InlineKeyboardButton("🎯 Quota Total", callback_data="taskedit:quota_total"),
         InlineKeyboardButton("👤 Quota Staff", callback_data="taskedit:quota_per_staff")],
        [InlineKeyboardButton("⏰ Deadline",    callback_data="taskedit:deadline")],
        [InlineKeyboardButton("❌ Batal",        callback_data=f"task:detail:{task_id}")],
    ])
    await update.callback_query.message.reply_text(
        f"✏️ *Edit Task* `{task_id}`\n\nPilih field yang ingin diubah:",
        parse_mode="Markdown",
        reply_markup=kb
    )
    return ET_FIELD


async def cb_taskedit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    field = update.callback_query.data.split(":")[1]
    context.user_data["edit_task_field"] = field

    labels = {
        "title": "Judul baru",
        "description": "Deskripsi baru (atau `-` untuk kosong)",
        "sheet_tab": "Nama tab Google Sheet baru",
        "repeat_type": "Repeat type baru (`daily` / `weekly` / `once`)",
        "quota_total": "Kuota total URL baru (angka)",
        "quota_per_staff": "Kuota per staff baru (angka)",
        "deadline": "Deadline baru (format: `HH:MM`) atau `-` untuk hapus",
    }
    await update.callback_query.message.reply_text(
        f"✏️ {labels.get(field, field)}:",
        parse_mode="Markdown",
        reply_markup=back_keyboard(f"task:edit:{context.user_data.get('edit_task_id', '')}")
    )
    return ET_VALUE


async def et_get_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field   = context.user_data.get("edit_task_field")
    task_id = context.user_data.get("edit_task_id")
    raw     = update.message.text.strip()
    actor   = await get_or_create_user(update)

    if not field or not task_id:
        await update.message.reply_text("❌ Sesi edit berakhir, mulai ulang.")
        return ConversationHandler.END

    # Konversi nilai berdasarkan tipe field
    if field in ("quota_total", "quota_per_staff"):
        try:
            value = int(raw)
        except ValueError:
            await update.message.reply_text("❌ Masukkan angka."); return ET_VALUE
    elif field == "repeat_type":
        if raw.lower() not in ("daily", "weekly", "once"):
            await update.message.reply_text("❌ Pilih: daily | weekly | once"); return ET_VALUE
        value = raw.lower()
    elif field == "deadline":
        if raw == "-":
            value = None
        else:
            try:
                today = datetime.now(TZ).date()
                hhmm  = datetime.strptime(raw, "%H:%M").time()
                value = datetime.combine(today, hhmm).replace(tzinfo=TZ).isoformat()
            except ValueError:
                await update.message.reply_text("❌ Format salah, gunakan HH:MM."); return ET_VALUE
    elif field == "description" and raw == "-":
        value = ""
    else:
        value = raw

    await fdb.update_task(task_id, **{field: value})
    await fdb.add_audit_log(actor["user_id"], "task.edit", "task", task_id, {"field": field, "value": str(value)})

    assigned_count = 0
    if field == "quota_per_staff":
        today_str = datetime.now(TZ).date().isoformat()
        newly_assigned_urls = await fdb.sync_task_assignments(task_id, today_str)
        if newly_assigned_urls:
            assigned_count = len(newly_assigned_urls)
            task = await fdb.get_task(task_id)
            tab = task.get("sheet_tab", "Sheet1") if task else "Sheet1"
            
            async def bg_update_assigned_sheets(urls, sheet_tab):
                from bot.services.sheet_parser import update_sheet_status
                for u in urls:
                    try:
                        u_id = int(u["verified_by"])
                        user_obj = await fdb.get_user(u_id)
                        if user_obj:
                            username = user_obj.get("username")
                            full_name = user_obj.get("full_name")
                            staff_str = f"@{username}" if username else (full_name if full_name else str(u_id))
                        else:
                            staff_str = str(u_id)
                        status_str = f"ASSIGNED - {staff_str}"
                        await update_sheet_status(u["payment_url"], status_str, tab_name=sheet_tab, staff_info=staff_str)
                    except Exception as e:
                        logger.error(f"[SyncQuota] Gagal update status sheet untuk {u['payment_url']}: {e}")
            
            asyncio.create_task(bg_update_assigned_sheets(newly_assigned_urls, tab))

    # Cek overlapping daily tasks
    active_tasks = await fdb.list_tasks(status="active")
    daily_active = [t for t in active_tasks if t.get("repeat_type") == "daily"]
    warning_note = ""
    if len(daily_active) >= 2:
        warning_note = (
            "\n⚠️ *Peringatan Dev/Admin:*\n"
            f"Terdapat *{len(daily_active)} task daily* aktif yang berjalan bersamaan hari ini.\n"
            "Hal ini berisiko menumpuk jadwal/beban kerja harian staff. Pastikan ini disengaja.\n"
        )

    info_note = ""
    if assigned_count > 0:
        info_note = f"\n🔄 *Sinkronisasi Quota:* Berhasil menambahkan *{assigned_count}* link baru ke staff untuk memenuhi quota baru."

    await update.message.reply_text(
        f"✅ Task `{task_id}` berhasil diupdate!\n`{field}` → `{value}`{warning_note}{info_note}",
        parse_mode="Markdown",
        reply_markup=back_keyboard("menu:manage_tasks")
    )
    context.user_data.clear()
    return ConversationHandler.END


async def et_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Edit task dibatalkan.", reply_markup=back_keyboard("menu:manage_tasks"))
    return ConversationHandler.END


# Callbacks
async def cb_menu_config_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await cmd_config_task(update, context)


async def cb_menu_manage_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await cmd_list_tasks(update, context)


async def cb_menu_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await cmd_report(update, context)


async def cb_menu_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await cmd_users(update, context)


async def cb_menu_devtools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    text = (
        "🔧 *DEV TOOLS & CONTROL PANEL*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Silakan pilih aksi manajemen sistem di bawah ini:\n\n"
        "👥 *User Management*:\n"
        "  - Kelola status pendaftaran user baru\n"
        "  - Broadcast pesan ke seluruh staff aktif\n\n"
        "📊 *Task & Synchronization*:\n"
        "  - Buat/edit quota dan deadline task harian\n"
        "  - Sinkronisasi URL baru dari Sheets ke Database\n"
        "  - Kirim data penugasan staff ke Sheets\n\n"
        "🔑 *Verification & Database*:\n"
        "  - Re-verifikasi URL Stripe gagal atau reset status\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([
        # ── User Management ──────────────────────────────────
        [InlineKeyboardButton("👥 Daftar User",          callback_data="dev:users"),
         InlineKeyboardButton("📢 Broadcast",            callback_data="dev:broadcast_prompt")],
        # ── Task & URL ───────────────────────────────────────
        [InlineKeyboardButton("📋 Manage Tasks",         callback_data="menu:manage_tasks")],
        [InlineKeyboardButton("🔄 Sync Sheet → DB",      callback_data="dev:sync"),
         InlineKeyboardButton("📤 Push Assign → Sheet",  callback_data="dev:push_assignments")],
        [InlineKeyboardButton("🔁 Retry Failed (PENDING)",callback_data="dev:retry_failed"),
         InlineKeyboardButton("🔍 Verif Ulang Gagal",    callback_data="dev:verify_failed")],
        [InlineKeyboardButton("🗑️ Reset Hari Ini",       callback_data="dev:reset_today"),
         InlineKeyboardButton("⚡ Verif Semua",           callback_data="dev:verify_all")],
        # ── Nav ──────────────────────────────────────────────
        [InlineKeyboardButton("🔙 Kembali",              callback_data="menu:main")],
    ])
    try:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ── Dev action callbacks ─────────────────────────────────────────────────────

async def _dev_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    """Dispatcher: jalankan perintah dev via tombol inline."""
    await update.callback_query.answer(f"⏳ Memproses {action}...")
    msg = update.callback_query.message

    if action == "users":
        # Simulasikan /users
        fake = type("U", (), {"message": msg, "effective_user": update.effective_user})()
        fake.message = type("M", (), {
            "reply_text": msg.reply_text,
            "from_user": update.effective_user,
        })()
        context._fake_update = True
        await cmd_users(update, context)

    elif action == "sync":
        progress_msg = await msg.reply_text("⏳ *Sync Sheet → DB dimulai...*", parse_mode="Markdown")
        from bot.handlers.verif import _sync_sheet_to_db
        from datetime import datetime as _dt
        today = _dt.now(TZ).date().isoformat()
        all_tasks = await fdb.list_tasks()
        results = []
        for i, t in enumerate(all_tasks):
            try:
                await progress_msg.edit_text(
                    f"⏳ *Sync Sheet → DB ({i}/{len(all_tasks)})...*\n"
                    f"Sedang sinkronisasi task: `{t['id'][:20]}...`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            count, err = await _sync_sheet_to_db(t, today)
            results.append(f"• `{t['id'][:20]}`: +{count} URL" + (f" ⚠️{err}" if err else ""))
        try:
            await progress_msg.edit_text(
                "✅ *Sync Selesai!*\n" + "\n".join(results) if results else "ℹ️ Tidak ada task aktif.",
                parse_mode="Markdown"
            )
        except Exception:
            await msg.reply_text(
                "✅ *Sync Selesai!*\n" + "\n".join(results) if results else "ℹ️ Tidak ada task aktif.",
                parse_mode="Markdown"
            )

    elif action == "push_assignments":
        # Jalankan langsung logic push_assignments
        class _FakeUpdate:
            callback_query = None
            effective_user = update.effective_user
            class message:
                @staticmethod
                async def reply_text(text, **kw): return await msg.reply_text(text, **kw)
        await cmd_push_assignments(_FakeUpdate(), context)

    elif action == "push_status":
        class _FakeUpdate:
            callback_query = None
            effective_user = update.effective_user
            class message:
                @staticmethod
                async def reply_text(text, **kw): return await msg.reply_text(text, **kw)
        await cmd_push_verified_status(_FakeUpdate(), context)

    elif action == "retry_failed":
        await msg.reply_text("⏳ *Me-reset URL gagal ke PENDING...*", parse_mode="Markdown")
        from datetime import datetime as _dt
        today = _dt.now(TZ).date().isoformat()
        count = await fdb.retry_failed_urls(today)
        await msg.reply_text(
            f"✅ `{count}` URL di-reset ke PENDING." if count else "ℹ️ Tidak ada URL gagal hari ini.",
            parse_mode="Markdown"
        )

    elif action == "verify_failed":
        class _FakeUpdate:
            callback_query = None
            effective_user = update.effective_user
            class message:
                @staticmethod
                async def reply_text(text, **kw): return await msg.reply_text(text, **kw)
        await cmd_verify_failed(_FakeUpdate(), context)

    elif action == "verify_all":
        class _FakeUpdate:
            callback_query = None
            effective_user = update.effective_user
            class message:
                @staticmethod
                async def reply_text(text, **kw): return await msg.reply_text(text, **kw)
        await cmd_verify_all(_FakeUpdate(), context)

    elif action == "reset_today":
        confirm_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Ya, Reset!", callback_data="dev:reset_today_confirm"),
            InlineKeyboardButton("❌ Batal",      callback_data="menu:devtools"),
        ]])
        await msg.reply_text(
            "⚠️ *Yakin hapus semua data URL & progress hari ini?*\n"
            "Tindakan ini tidak bisa dibatalkan!",
            parse_mode="Markdown", reply_markup=confirm_kb
        )

    elif action == "reset_today_confirm":
        from datetime import datetime as _dt
        today = _dt.now(TZ).date().isoformat()
        urls_del, prog_del = await fdb.reset_today(today)
        await msg.reply_text(
            f"✅ *Reset Selesai!*\n• URL dihapus: `{urls_del}`\n• Progress dihapus: `{prog_del}`",
            parse_mode="Markdown"
        )

    elif action == "backup":
        await msg.reply_text("⏳ *Backup ke SQLite...*", parse_mode="Markdown")
        from bot.backup import backup_postgres_to_sqlite
        ok, info = await asyncio.to_thread(backup_postgres_to_sqlite)
        await msg.reply_text(
            f"{'✅' if ok else '❌'} *{'Backup Berhasil' if ok else 'Backup Gagal'}!*\n`{info}`",
            parse_mode="Markdown"
        )

    elif action == "restore":
        await msg.reply_text("⏳ *Restore dari SQLite ke PostgreSQL...*", parse_mode="Markdown")
        from bot.backup import restore_sqlite_to_postgres
        ok, info = await asyncio.to_thread(restore_sqlite_to_postgres)
        await msg.reply_text(
            f"{'✅' if ok else '❌'} *{'Restore Berhasil' if ok else 'Restore Gagal'}!*\n`{info}`",
            parse_mode="Markdown"
        )


@require_role("admin", "dev")
async def cb_dev_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.callback_query.data.split(":", 1)[1]
    await _dev_action(update, context, action)



async def cb_menu_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    text = (
        "🌐 *DASHBOARD MONITORING*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Akses dashboard real-time melalui link berikut:\n\n"
        f"🔗 [Buka Dashboard Web]({DASHBOARD_URL})\n\n"
        "_Pastikan Anda login menggunakan akun Telegram yang terdaftar._"
    )
    await update.callback_query.message.reply_text(
        text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=back_keyboard()
    )





@require_role("admin", "dev")
async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ *Memulai proses SQLite backup lokal dari PostgreSQL...*", parse_mode="Markdown")
    from bot.backup import backup_postgres_to_sqlite
    success, msg = await asyncio.to_thread(backup_postgres_to_sqlite)
    if success:
        await update.message.reply_text(f"✅ *Backup Berhasil!*\n\n`{msg}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ *Backup Gagal!*\n\n`{msg}`", parse_mode="Markdown")


@require_role("admin", "dev")
async def cmd_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ *Memulai proses pemulihan dari SQLite lokal ke PostgreSQL...*", parse_mode="Markdown")
    from bot.backup import restore_sqlite_to_postgres
    success, msg = await asyncio.to_thread(restore_sqlite_to_postgres)
    if success:
        await update.message.reply_text(f"✅ *Restore Berhasil!*\n\n`{msg}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ *Restore Gagal!*\n\n`{msg}`", parse_mode="Markdown")


@require_role("admin", "dev")
async def cmd_reset_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ *Memulai proses reset database hari ini...*", parse_mode="Markdown")
    try:
        today_str = datetime.now(TZ).date().isoformat()
        urls_del, prog_del = await fdb.reset_today(today_str)
        await update.message.reply_text(
            f"✅ *Reset Database Berhasil!*\n\n"
            f"• Tanggal: `{today_str}`\n"
            f"• URL terhapus: `{urls_del}`\n"
            f"• Progress terhapus: `{prog_del}`\n\n"
            f"_Anda sekarang dapat melakukan Sync Sheet kembali._",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ *Reset Database Gagal!*\n\n`{e}`", parse_mode="Markdown")


@require_role("admin", "dev")
async def cmd_retry_failed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ *Memproses ulang semua URL yang gagal/timeout hari ini...*", parse_mode="Markdown")
    try:
        today_str = datetime.now(TZ).date().isoformat()
        count = await fdb.retry_failed_urls(today_str)
        if count > 0:
            await update.message.reply_text(
                f"✅ *Berhasil Me-reset URL!*\n\n"
                f"• Tanggal: `{today_str}`\n"
                f"• Jumlah URL di-reset ke PENDING: `{count}`\n\n"
                f"_URL tersebut sekarang dapat diambil dan diverifikasi kembali oleh staff._",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"ℹ️ Tidak ada URL gagal (TIMEOUT/HTTP_ERR/FORMAT_ERR) untuk hari ini (`{today_str}`).",
                parse_mode="Markdown"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ *Gagal me-reset URL:* `{e}`", parse_mode="Markdown")


@require_role("admin", "dev")
async def cmd_verify_failed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update)

    # Gunakan UTC sebagai patokan tanggal hari ini
    from datetime import timezone
    today_utc = datetime.now(timezone.utc).date().isoformat()

    status_msg = await update.message.reply_text(
        f"⏳ *Memulai Re-verifikasi & Rekonsiliasi dengan Google Sheets ({today_utc} UTC)...*",
        parse_mode="Markdown"
    )

    try:
        from bot.services.sheet_parser import reconcile_and_verify_failed_urls

        last_edit_time = 0
        async def progress_cb(current, total):
            nonlocal last_edit_time
            import time
            now = time.time()
            if now - last_edit_time > 1.5 or current == total:
                last_edit_time = now
                try:
                    await status_msg.edit_text(
                        f"⏳ *Memproses Re-verifikasi... ({current}/{total})*\n"
                        f"Mengecek link di database dan menyinkronkan status...",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

        res = await reconcile_and_verify_failed_urls(today_utc, actor_id=user["user_id"], progress_callback=progress_cb)

        await update.message.reply_text(
            f"✅ *Re-verifikasi Selesai — {today_utc} (UTC)*\n\n"
            f"*Sync dari Sheets:*\n"
            f"  • Sudah disubmit (skip reverif): `{res['already_done_count']}`\n"
            f"  • DB diupdate → OK             : `{res['sync_ok_count']}`\n\n"
            f"*Re-verifikasi ({res['reverif_ok'] + res['reverif_fail']} URL):*\n"
            f"  • 🟢 OK (expired/done)  : `{res['reverif_ok']}`\n"
            f"  • 🟡 Masih aktif/gagal  : `{res['reverif_fail']}`\n\n"
            f"_🟢 = link tidak bisa diakses (sudah expired/digunakan)_\n"
            f"_🟡 = link Stripe masih aktif (belum dibayar)_",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.exception(f"[VerifyFailed] Error: {e}")
        try:
            await status_msg.edit_text(f"❌ *Proses Re-verifikasi Gagal:* `{e}`")
        except Exception:
            await update.message.reply_text(f"❌ *Proses Re-verifikasi Gagal:* `{e}`", parse_mode="Markdown")


@require_role("admin", "dev")
async def cmd_verify_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update)
    from datetime import timezone
    today_utc = datetime.now(timezone.utc).date().isoformat()

    status_msg = await update.message.reply_text(
        f"⏳ *Memulai Verifikasi Massal & Update Sheets untuk Semua Link Hari Ini ({today_utc} UTC)...*",
        parse_mode="Markdown"
    )

    try:
        from bot.services.sheet_parser import verify_all_urls_today

        last_edit_time = 0
        async def progress_cb(current, total):
            nonlocal last_edit_time
            import time
            now = time.time()
            if now - last_edit_time > 1.5 or current == total:
                last_edit_time = now
                try:
                    await status_msg.edit_text(
                        f"⏳ *Memproses Verifikasi Massal... ({current}/{total})*\n"
                        f"Mengecek Stripe & Leonardo API Key serta menulis status ke Sheets...",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

        res = await verify_all_urls_today(today_utc, actor_id=user["user_id"], progress_callback=progress_cb)

        await update.message.reply_text(
            f"✅ *Verifikasi Massal Selesai — {today_utc} (UTC)*\n\n"
            f"  • Total URL Diproses : `{res['total']}`\n"
            f"  • 🟢 OK              : `{res['ok']}`\n"
            f"  • 🟡 FAIL / HTTP_ERR : `{res['fail']}`\n\n"
            f"_Seluruh status hasil akhir verifikasi telah diperbarui di Google Sheets._",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception(f"[VerifyAll] Error: {e}")
        try:
            await status_msg.edit_text(f"❌ *Verifikasi Massal Gagal:* `{e}`")
        except Exception:
            await update.message.reply_text(f"❌ *Verifikasi Massal Gagal:* `{e}`", parse_mode="Markdown")



@require_role("admin", "dev")
async def cmd_sync_sheets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ *Memulai sinkronisasi spreadsheet untuk semua active task ke PostgreSQL...*", parse_mode="Markdown")
    from bot.scheduler import job_sync_spreadsheets
    try:
        await job_sync_spreadsheets(context.application)
        await update.message.reply_text("✅ *Sinkronisasi Google Sheets selesai!*", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ *Sinkronisasi Gagal!*\n\n`{e}`", parse_mode="Markdown")


@require_role("admin", "dev")
async def cmd_push_assignments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Push semua assignment hari ini dari PostgreSQL ke Google Sheets.
    Berguna jika URL sudah assigned di DB tapi Sheets belum ter-update.
    """
    from datetime import timezone
    from bot.services.sheet_parser import update_sheet_status

    today_utc = datetime.now(timezone.utc).date().isoformat()
    status_msg = await update.message.reply_text(
        f"⏳ *Menyinkronkan assignment ke Google Sheets ({today_utc} UTC)...*",
        parse_mode="Markdown"
    )

    try:
        # Ambil semua URL hari ini yang punya verified_by (sudah assigned ke seseorang)
        # status bisa PENDING, PROCESSING, HTTP_ERR, OK, dll — yang penting punya assigned staff
        all_tasks = await fdb.list_tasks()
        task_tab_map = {t["id"]: t.get("sheet_tab", "Sheet1") for t in all_tasks}

        # Query semua URL hari ini yang punya verified_by
        total_pushed = 0
        total_skipped = 0
        errors = 0

        sem = asyncio.Semaphore(5)

        for task in all_tasks:
            task_id = task["id"]
            tab = task_tab_map.get(task_id, "Sheet1")

            # Ambil URL yang sudah assigned (verified_by != NULL) dan masih PROCESSING
            urls, _ = await fdb.list_sheet_urls(
                task_id=task_id, date=today_utc,
                status="PROCESSING", limit=500
            )

            for u in urls:
                verified_by_id = u.get("verified_by")
                if not verified_by_id:
                    total_skipped += 1
                    continue

                try:
                    staff_user = await fdb.get_user(int(verified_by_id))
                    if not staff_user:
                        total_skipped += 1
                        continue
                    username  = staff_user.get("username")
                    full_name = staff_user.get("full_name")
                    staff_str = f"@{username}" if username else (full_name if full_name else str(verified_by_id))
                    status_str = f"ASSIGNED - {staff_str}"

                    async def _push(purl, sstr, sinfo, tname):
                        async with sem:
                            try:
                                await update_sheet_status(purl, sstr, tab_name=tname, staff_info=sinfo)
                                return True
                            except Exception as e:
                                logger.warning(f"[PushAssign] Gagal: {purl}: {e}")
                                return False

                    ok = await _push(u["payment_url"], status_str, staff_str, tab)
                    if ok:
                        total_pushed += 1
                    else:
                        errors += 1

                except Exception as e:
                    logger.error(f"[PushAssign] Error user {verified_by_id}: {e}")
                    errors += 1

        await update.message.reply_text(
            f"✅ *Push Assignment Selesai ({today_utc} UTC)*\n\n"
            f"• Berhasil dikirim ke Sheets : `{total_pushed}`\n"
            f"• Dilewati (tidak ada staff) : `{total_skipped}`\n"
            f"• Error                      : `{errors}`\n\n"
            f"_Kolom F: ASSIGNED-@staff, Kolom G: nama staff_",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.exception(f"[PushAssign] Fatal error: {e}")
        await status_msg.edit_text(f"❌ *Gagal:* `{e}`")


@require_role("admin", "dev")
async def cmd_push_verified_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import timezone
    from bot.services.sheet_parser import update_sheet_status

    today_utc = datetime.now(timezone.utc).date().isoformat()

    status_msg = await update.message.reply_text(
        "⏳ *Mengambil data verifikasi hari ini untuk dikirim ke Sheets...*",
        parse_mode="Markdown"
    )

    try:
        all_tasks = await fdb.list_tasks()
        task_tab_map = {t["id"]: t.get("sheet_tab", "Sheet1") for t in all_tasks}

        total_pushed = 0
        errors = 0

        sem = asyncio.Semaphore(5)

        for task in all_tasks:
            task_id = task["id"]
            tab = task_tab_map.get(task_id, "Sheet1")

            # Ambil semua URL hari ini dari DB
            urls, _ = await fdb.list_sheet_urls(
                task_id=task_id, date=today_utc, limit=1000
            )

            # Filter yang statusnya terverifikasi (bukan PENDING/PROCESSING)
            verified_urls = [u for u in urls if u.get("status") not in ("PENDING", "PROCESSING")]

            async def _push_one(url_obj):
                nonlocal total_pushed, errors
                purl = url_obj["payment_url"]
                status = url_obj["status"]
                verified_by_id = url_obj.get("verified_by")

                staff_str = "System-Push"
                if verified_by_id:
                    try:
                        staff_user = await fdb.get_user(int(verified_by_id))
                        if staff_user:
                            username = staff_user.get("username")
                            full_name = staff_user.get("full_name")
                            staff_str = f"@{username}" if username else (full_name if full_name else str(verified_by_id))
                    except Exception:
                        pass

                async with sem:
                    try:
                        # 1. Tulis info ASSIGNED dulu ke Kolom F (Assigned By) via Google Sheets logic
                        assign_status = f"ASSIGNED - {staff_str}"
                        await update_sheet_status(purl, assign_status, tab_name=tab, staff_info=staff_str)

                        # 2. Tulis status final (OK / HTTP_ERR / dll.) ke Kolom G & H (Verified By)
                        ok = await update_sheet_status(purl, status, tab_name=tab, staff_info=staff_str)
                        if ok:
                            total_pushed += 1
                        else:
                            errors += 1
                    except Exception as e:
                        logger.warning(f"[PushStatus] Gagal push {purl}: {e}")
                        errors += 1

            if verified_urls:
                tasks_to_run = [_push_one(u) for u in verified_urls]
                await asyncio.gather(*tasks_to_run)

        await update.message.reply_text(
            f"✅ *Push Status Selesai ({today_utc} UTC)*\n\n"
            f"• Berhasil ditulis ulang ke Sheets : `{total_pushed}`\n"
            f"• Error                              : `{errors}`\n\n"
            f"_Seluruh status verifikasi berhasil disinkronisasikan ke Google Sheets._",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception(f"[PushStatus] Fatal error: {e}")
        await update.message.reply_text(f"❌ *Gagal push status:* `{e}`", parse_mode="Markdown")


def get_handlers():
    config_conv = ConversationHandler(
        entry_points=[
            CommandHandler("config_task", cmd_config_task),
            CallbackQueryHandler(cb_menu_config_task, pattern="^menu:config_task$"),
        ],
        states={
            CT_TITLE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, ct_get_title)],
            CT_DESC:        [MessageHandler(filters.TEXT & ~filters.COMMAND, ct_get_desc)],
            CT_TAB:         [MessageHandler(filters.TEXT & ~filters.COMMAND, ct_get_tab)],
            CT_QUOTA_TOTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ct_get_quota_total)],
            CT_QUOTA_STAFF: [MessageHandler(filters.TEXT & ~filters.COMMAND, ct_get_quota_staff)],
            CT_DEADLINE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ct_get_deadline)],
            CT_REPEAT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ct_get_repeat)],
        },
        fallbacks=[CommandHandler("cancel", ct_cancel)],
        allow_reentry=True,
    )

    edit_task_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_task_edit, pattern="^task:edit:"),
        ],
        states={
            ET_FIELD: [CallbackQueryHandler(cb_taskedit_field, pattern="^taskedit:")],
            ET_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, et_get_value)],
        },
        fallbacks=[CommandHandler("cancel", et_cancel)],
        allow_reentry=True,
    )

    return [
        config_conv,
        edit_task_conv,
        CommandHandler("approve",       cmd_approve),
        CommandHandler("unban",         cmd_unban),
        CommandHandler("setrole",       cmd_setrole),
        CommandHandler("users",         cmd_users),
        CommandHandler("report",        cmd_report),
        CommandHandler("broadcast",     cmd_broadcast),
        CommandHandler("backup",        cmd_backup),
        CommandHandler("restore",       cmd_restore),
        CommandHandler("sync",          cmd_sync_sheets),
        CommandHandler("reset_today",   cmd_reset_today),
        CommandHandler("retry_failed",  cmd_retry_failed),
        CommandHandler("verify_failed",    cmd_verify_failed),
        CommandHandler("verify_all",       cmd_verify_all),
        CommandHandler("push_assignments",  cmd_push_assignments),
        CommandHandler("push_status",       cmd_push_verified_status),
        CommandHandler("tasks",             cmd_list_tasks),
        CallbackQueryHandler(cb_menu_report,        pattern="^menu:report$"),
        CallbackQueryHandler(cb_menu_users,         pattern="^menu:users$"),
        CallbackQueryHandler(cb_menu_devtools,      pattern="^menu:devtools$"),
        CallbackQueryHandler(cb_dev_action,          pattern="^dev:"),
        CallbackQueryHandler(cb_menu_dashboard,     pattern="^menu:dashboard$"),
        CallbackQueryHandler(cb_menu_manage_tasks,  pattern="^menu:manage_tasks$"),
        CallbackQueryHandler(cb_task_detail,        pattern="^task:detail:"),
        CallbackQueryHandler(cb_task_sync_sheet,    pattern="^task:sync:"),
        CallbackQueryHandler(cb_task_pause,         pattern="^task:pause:"),
        CallbackQueryHandler(cb_task_activate,      pattern="^task:activate:"),
        CallbackQueryHandler(cb_task_delete_confirm,pattern="^task:delete_confirm:"),
        CallbackQueryHandler(cb_task_delete_do,     pattern="^task:delete_do:"),
    ]

