"""
handlers/admin.py — Admin/Dev commands (Firebase version)
"""
from __future__ import annotations

from datetime import datetime

from telegram import Update
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)

import bot.firebase_db as fdb
from bot.middlewares.auth import get_or_create_user, require_role
from bot.utils.keyboards import back_keyboard
from bot.utils.formatters import role_badge, progress_bar, now_wib
from bot.config import TZ, DEV_IDS, DASHBOARD_URL

(CT_TITLE, CT_DESC, CT_TAB, CT_QUOTA_TOTAL, CT_QUOTA_STAFF, CT_DEADLINE, CT_REPEAT) = range(7)


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

    await update.message.reply_text(
        f"✅ *Task berhasil dibuat!*\n\n"
        f"ID    : `{task_id}`\n"
        f"Judul : {task_data['title']}\n"
        f"Tab   : {task_data['sheet_tab']}\n"
        f"Repeat: {val}\n\n"
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


# Callbacks
async def cb_menu_config_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await cmd_config_task(update, context)


async def cb_menu_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await cmd_report(update, context)


async def cb_menu_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await cmd_users(update, context)


async def cb_menu_devtools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    text = (
        "🔧 *DEV TOOLS*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Gunakan perintah berikut secara langsung di chat:\n\n"
        "• `/users` — Daftar & kelola semua user\n"
        "• `/approve <user_id>` — Approve pendaftaran manual\n"
        "• `/setrole <user_id> <role>` — Ubah role user\n"
        "• `/broadcast <pesan>` — Kirim pesan broadcast ke semua staff\n"
    )
    await update.callback_query.message.reply_text(
        text, parse_mode="Markdown", reply_markup=back_keyboard()
    )


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


async def cb_menu_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    text = (
        "🔔 *SET REMINDER*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Fitur pengingat otomatis berjalan setiap hari pukul *22:00 WIB* "
        "untuk mengirim ringkasan laporan harian kepada Admin dan Dev.\n\n"
        "_Pengaturan pengingat kustom lewat bot akan segera hadir._"
    )
    await update.callback_query.message.reply_text(
        text, parse_mode="Markdown", reply_markup=back_keyboard()
    )


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
    return [
        config_conv,
        CommandHandler("approve",   cmd_approve),
        CommandHandler("setrole",   cmd_setrole),
        CommandHandler("users",     cmd_users),
        CommandHandler("report",    cmd_report),
        CommandHandler("broadcast", cmd_broadcast),
        CallbackQueryHandler(cb_menu_report, pattern="^menu:report$"),
        CallbackQueryHandler(cb_menu_users,  pattern="^menu:users$"),
        CallbackQueryHandler(cb_menu_devtools,  pattern="^menu:devtools$"),
        CallbackQueryHandler(cb_menu_dashboard, pattern="^menu:dashboard$"),
        CallbackQueryHandler(cb_menu_reminder,  pattern="^menu:reminder$"),
    ]

