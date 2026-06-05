"""
handlers/task.py — /task /progress /history (Firebase version)
"""
from __future__ import annotations

from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import bot.firebase_db as fdb
from bot.middlewares.auth import get_or_create_user, require_approved
from bot.utils.keyboards import back_keyboard
from bot.utils.formatters import progress_bar, now_wib, format_date_id, task_status_badge
from bot.config import TZ


@require_approved
async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(TZ).date().isoformat()
    tasks = await fdb.list_tasks(status="active")

    if not tasks:
        await update.message.reply_text(
            "📭 Tidak ada task aktif hari ini.",
            reply_markup=back_keyboard()
        )
        return

    lines = [
        f"📋 *TASK HARI INI*\n"
        f"📅 {format_date_id(now_wib())}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    ]

    for task in tasks:
        total = await fdb.count_sheet_urls(task["task_id"], today)
        done  = await fdb.count_sheet_urls(task["task_id"], today, status="OK")
        quota = task.get("quota_total", 0)
        bar   = progress_bar(done, total if total > 0 else quota)
        deadline_str = (
            task["deadline"][:16].replace("T", " ") + " WIB"
            if task.get("deadline") else "—"
        )
        lines.append(
            f"\n📌 `{task['task_id']}`\n"
            f"   {task['title']}\n"
            f"   Progress : {bar}\n"
            f"   Deadline : {deadline_str}\n"
            f"   Status   : {task_status_badge(task['status'])}"
        )

    lines.append("\n\n👉 Gunakan /verif untuk memulai verifikasi URL.")
    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=back_keyboard()
    )


@require_approved
async def cmd_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = await get_or_create_user(update)
    today = datetime.now(TZ).date().isoformat()
    progs = await fdb.list_progress_by_user(user["user_id"], limit=10)
    today_progs = [p for p in progs if p["date"] == today]

    if not today_progs:
        await update.message.reply_text(
            "📊 Belum ada progress hari ini.\nMulai dengan /verif",
            reply_markup=back_keyboard()
        )
        return

    lines = [f"📊 *PROGRESS SAYA — {today}*\n━━━━━━━━━━━━━━━━━━━━"]
    for p in today_progs:
        task = await fdb.get_task(p["task_id"])
        title = task["title"][:30] if task else p["task_id"]
        lines.append(
            f"\n📌 {title}\n"
            f"   Diverif : {p['submitted']}\n"
            f"   ✅ OK    : {p['verified_ok']}\n"
            f"   ❌ Gagal : {p['verified_fail']}"
        )

    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=back_keyboard()
    )


@require_approved
async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update)
    args = context.args
    days = int(args[0]) if args and args[0].isdigit() else 7
    progs = await fdb.list_progress_by_user(user["user_id"], limit=days * 5)

    if not progs:
        await update.message.reply_text("📖 Belum ada riwayat.", reply_markup=back_keyboard())
        return

    lines = [f"📖 *RIWAYAT {days} HARI TERAKHIR*\n━━━━━━━━━━━━━━━━━━━━"]
    current_date = None
    for p in progs:
        if p["date"] != current_date:
            current_date = p["date"]
            lines.append(f"\n📅 *{p['date']}*")
        task  = await fdb.get_task(p["task_id"])
        title = task["title"][:25] if task else p["task_id"]
        lines.append(
            f"  • {title}: "
            f"{p['verified_ok']}✅ {p['verified_fail']}❌ / {p['submitted']} total"
        )

    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=back_keyboard()
    )


async def cb_menu_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    update.message = update.callback_query.message
    await cmd_task(update, context)


async def cb_menu_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    update.message = update.callback_query.message
    await cmd_progress(update, context)


async def cb_menu_verif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    from bot.handlers.verif import cmd_verif
    update.message = update.callback_query.message
    await cmd_verif(update, context)


def get_handlers():
    return [
        CommandHandler("task",     cmd_task),
        CommandHandler("progress", cmd_progress),
        CommandHandler("history",  cmd_history),
        CallbackQueryHandler(cb_menu_task,     pattern="^menu:task$"),
        CallbackQueryHandler(cb_menu_progress, pattern="^menu:progress$"),
        CallbackQueryHandler(cb_menu_verif,    pattern="^menu:verif$"),
        CallbackQueryHandler(cmd_history,      pattern="^menu:history$"),
    ]
