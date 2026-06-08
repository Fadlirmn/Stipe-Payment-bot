"""
handlers/start.py — /start, /menu, /help, /me (PostgreSQL version)
"""
from __future__ import annotations

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.db import get_user, update_user
import bot.db as fdb
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
        # Tombol inline langsung di pesan notifikasi admin
        approve_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Setujui",  callback_data=f"approve_user:{tg.id}"),
            InlineKeyboardButton("❌ Tolak",    callback_data=f"reject_user:{tg.id}"),
        ]])
        notif_text = (
            f"🔔 *Pendaftaran Baru*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Nama     : {tg.full_name}\n"
            f"🔗 Username : @{tg.username or 'N/A'}\n\n"
            f"Klik tombol di bawah untuk menyetujui atau menolak."
        )

        # Kumpulkan semua penerima: DEV_IDS + semua admin/dev aktif di database
        notify_ids = set(DEV_IDS)
        try:
            all_users = await fdb.list_users()
            for u in all_users:
                if u.get("role") in ("admin", "dev") and u.get("is_active", True):
                    notify_ids.add(u["user_id"])
        except Exception:
            pass

        for notify_id in notify_ids:
            try:
                await context.bot.send_message(
                    chat_id=notify_id,
                    text=notif_text,
                    parse_mode="Markdown",
                    reply_markup=approve_kb,
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


async def cb_menu_setemail_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    text = (
        "📧 *Set Email Dashboard*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Untuk mendaftarkan atau memperbarui email dashboard Anda, silakan ketik perintah berikut:\n\n"
        "`/setemail <email_anda>`\n\n"
        "Contoh:\n"
        "`/setemail budi@email.com`\n\n"
        "_Email ini akan divalidasi saat Anda mendaftar atau masuk ke Web Dashboard._"
    )
    await update.callback_query.message.reply_text(
        text, parse_mode="Markdown", reply_markup=back_keyboard()
    )


async def cb_approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin klik tombol ✅ Setujui langsung dari pesan notifikasi."""
    query = update.callback_query
    await query.answer()

    target_id = int(query.data.split(":")[1])
    actor     = await get_or_create_user(update)
    target    = await fdb.get_user(target_id)

    if not target:
        await query.edit_message_text("❌ User tidak ditemukan di database.")
        return

    if target.get("role") != "pending":
        await query.edit_message_text(
            f"ℹ️ Akun ini sudah punya role *{target.get('role')}* — tidak perlu disetujui lagi.",
            parse_mode="Markdown",
        )
        return

    await fdb.update_user(target_id, role="staff", approved_by=actor["user_id"])
    await fdb.add_audit_log(actor["user_id"], "user.approve", "user", str(target_id),
                             {"new_role": "staff"})

    # Edit pesan notifikasi — hapus tombol, tampilkan status
    await query.edit_message_text(
        f"✅ *{target.get('full_name')} sudah disetujui sebagai Staff!*\n"
        f"Disetujui oleh: {actor.get('full_name')}",
        parse_mode="Markdown",
    )

    # Notif ke staff yang baru disetujui
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"🎉 *Selamat, {target.get('full_name')}!*\n\n"
                f"Akun kamu sudah disetujui oleh Admin.\n"
                f"Ketik /menu untuk mulai bekerja. 🚀"
            ),
            parse_mode="Markdown",
        )
    except Exception:
        pass


async def cb_reject_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin klik tombol ❌ Tolak langsung dari pesan notifikasi."""
    query = update.callback_query
    await query.answer()

    target_id = int(query.data.split(":")[1])
    actor     = await get_or_create_user(update)
    target    = await fdb.get_user(target_id)

    if not target:
        await query.edit_message_text("❌ User tidak ditemukan di database.")
        return

    await fdb.update_user(target_id, is_active=False)
    await fdb.add_audit_log(actor["user_id"], "user.reject", "user", str(target_id), {})

    # Edit pesan notifikasi — hapus tombol, tampilkan status
    await query.edit_message_text(
        f"🚫 *{target.get('full_name')} ditolak.*\n"
        f"Ditolak oleh: {actor.get('full_name')}",
        parse_mode="Markdown",
    )

    # Notif ke user yang ditolak
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                "🚫 *Maaf, pendaftaran kamu belum bisa disetujui.*\n\n"
                "Silakan hubungi admin untuk informasi lebih lanjut."
            ),
            parse_mode="Markdown",
        )
    except Exception:
        pass


def get_handlers():
    return [
        CommandHandler("start", cmd_start),
        CommandHandler("menu",  cmd_menu),
        CommandHandler("me",    cmd_me),
        CommandHandler("setemail", cmd_setemail),
        CommandHandler("help",  cmd_help),
        CallbackQueryHandler(cb_menu_main,          pattern="^menu:main$"),
        CallbackQueryHandler(cb_menu_help,           pattern="^menu:help$"),
        CallbackQueryHandler(cb_menu_setemail_info,  pattern="^menu:setemail_info$"),
        CallbackQueryHandler(cb_approve_user,        pattern=r"^approve_user:\d+$"),
        CallbackQueryHandler(cb_reject_user,         pattern=r"^reject_user:\d+$"),
    ]
