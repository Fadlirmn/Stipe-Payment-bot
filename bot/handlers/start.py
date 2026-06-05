"""
handlers/start.py — /start, /menu, /help, /me (Firebase version)
"""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.firebase_db import get_user, update_user
from bot.middlewares.auth import get_or_create_user, require_approved
from bot.utils.keyboards import main_menu_keyboard, back_keyboard
from bot.utils.formatters import format_date_id, role_badge, now_wib
from bot.config import DEV_IDS


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update)
    tg   = update.effective_user

    if user.get("role") == "pending":
        await update.effective_message.reply_text(
            f"👋 Halo *{tg.first_name}*!\n\n"
            f"Akun Anda sedang menunggu persetujuan admin.\n"
            f"Mohon tunggu konfirmasi sebelum menggunakan bot ini.",
            parse_mode="Markdown",
        )
        for dev_id in DEV_IDS:
            try:
                await context.bot.send_message(
                    chat_id=dev_id,
                    text=(
                        f"🔔 *Pendaftaran Baru*\n"
                        f"Nama: {tg.full_name}\n"
                        f"Username: @{tg.username or 'N/A'}\n"
                        f"ID: `{tg.id}`\n\n"
                        f"Gunakan `/approve {tg.id}` untuk menyetujui."
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return

    await _show_main_menu(update, context, user)


@require_approved
async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update)
    await _show_main_menu(update, context, user)


async def _show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    now  = format_date_id(now_wib())
    text = (
        f"🤖 *STRIPE VERIF BOT v1.0*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 {user.get('full_name') or 'User'} • {role_badge(user.get('role',''))}\n"
        f"📅 {now}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Pilih menu di bawah:"
    )
    kb  = main_menu_keyboard(user.get("role", "staff"))
    msg = update.effective_message
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=kb)


@require_approved
async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_or_create_user(update)
    text = (
        f"👤 *Profil Saya*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Nama     : {user.get('full_name')}\n"
        f"Username : @{user.get('username') or 'N/A'}\n"
        f"ID       : `{user.get('user_id')}`\n"
        f"Email    : `{user.get('email') or '❌ Belum diatur'}`\n"
        f"Role     : {role_badge(user.get('role',''))}\n"
        f"Status   : {'✅ Aktif' if user.get('is_active') else '⛔ Nonaktif'}\n"
        f"Bergabung: {str(user.get('joined_at',''))[:10]}"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=back_keyboard())


@require_approved
async def cmd_setemail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ *Penggunaan:* `/setemail <email>`\n\n"
            "Contoh: `/setemail nama@email.com`\n\n"
            "_Email ini digunakan untuk mendaftar dan login ke Dashboard Vercel._",
            parse_mode="Markdown"
        )
        return

    email = args[0].strip().lower()
    import re
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text("❌ Format email tidak valid.")
        return

    await update_user(update.effective_user.id, email=email)

    await update.message.reply_text(
        f"✅ *Email berhasil disimpan!*\n\n"
        f"Email: `{email}`\n\n"
        f"Anda sekarang dapat menggunakan email ini untuk Mendaftar/Masuk di Dashboard.",
        parse_mode="Markdown"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Panduan Stripe Verif Bot*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*Perintah Dasar:*\n"
        "/start   — Registrasi & masuk bot\n"
        "/menu    — Buka menu utama\n"
        "/task    — Lihat task aktif hari ini\n"
        "/verif   — Mulai verifikasi URL dari sheet\n"
        "/progress — Progress saya hari ini\n"
        "/history  — Riwayat verifikasi\n"
        "/me       — Info profil saya\n"
        "/setemail — Hubungkan email untuk dashboard\n\n"
        "*Admin/Dev:*\n"
        "/config\\_task — Konfigurasi task\n"
        "/report       — Laporan tim\n"
        "/sync\\_sheet   — Sync URL dari spreadsheet\n\n"
        "*Dev:*\n"
        "/users   — Manajemen user\n"
        "/approve — Approve user baru\n"
        "/setrole — Ubah role user"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=back_keyboard())


async def cb_menu_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = await get_or_create_user(update)
    await _show_main_menu(update, context, user)


async def cb_menu_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Ketik /help untuk melihat panduan lengkap."
    )


def get_handlers():
    return [
        CommandHandler("start", cmd_start),
        CommandHandler("menu",  cmd_menu),
        CommandHandler("me",    cmd_me),
        CommandHandler("setemail", cmd_setemail),
        CommandHandler("help",  cmd_help),
        CallbackQueryHandler(cb_menu_main, pattern="^menu:main$"),
        CallbackQueryHandler(cb_menu_help, pattern="^menu:help$"),
    ]
