"""
main.py — Entry point bot (PostgreSQL version)
"""
import asyncio
from loguru import logger
from telegram.ext import Application, ContextTypes

from bot.config import BOT_TOKEN
from bot.db import init_db
from bot.scheduler import setup_scheduler

from bot.handlers import start, task, verif, admin
import telegram.error


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error occurring during update handling."""
    err = context.error
    if isinstance(err, telegram.error.BadRequest) and "Query is too old" in str(err):
        logger.warning(f"[Telegram] Callback query expired (Query is too old): {err}")
        return
    if isinstance(err, telegram.error.TimedOut):
        logger.warning(f"[Telegram] Request timed out: {err}")
        return
    logger.exception(f"[Telegram] Exception while handling an update:", exc_info=err)


from telegram import BotCommand

async def post_init(application: Application) -> None:
    await init_db()
    logger.info("✅ PostgreSQL connected")
    
    # Set bot commands list in Telegram UI
    commands = [
        BotCommand("start", "Registrasi & masuk bot"),
        BotCommand("menu", "Buka menu utama"),
        BotCommand("help", "Panduan lengkap"),
        BotCommand("me", "Info profil saya"),
        BotCommand("setemail", "Hubungkan email untuk dashboard"),
        BotCommand("verif", "Mulai verifikasi URL"),
        BotCommand("progress", "Progress verifikasi saya"),
        BotCommand("history", "Riwayat verifikasi"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("✅ Bot commands registered in Telegram")
    except Exception as e:
        logger.warning(f"⚠️ Gagal mendaftarkan commands ke Telegram: {e}")
    
    scheduler = setup_scheduler(application)
    scheduler.start()
    logger.info("✅ Scheduler started")



def main():
    logger.info("🚀 Starting Stripe Verif Bot (PostgreSQL)...")
    
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    
    app.add_error_handler(error_handler)
    
    for handler in start.get_handlers():   app.add_handler(handler)
    for handler in task.get_handlers():    app.add_handler(handler)
    for handler in verif.get_handlers():   app.add_handler(handler)
    for handler in admin.get_handlers():   app.add_handler(handler)
    
    logger.info("✅ Bot polling started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

