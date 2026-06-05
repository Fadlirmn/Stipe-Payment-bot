"""
main.py — Entry point bot (Firebase version)
"""
import asyncio
from loguru import logger
from telegram.ext import Application

from bot.config import BOT_TOKEN
from bot.firebase_db import init_db
from bot.scheduler import setup_scheduler

from bot.handlers import start, task, verif, admin


def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    for handler in start.get_handlers():   app.add_handler(handler)
    for handler in task.get_handlers():    app.add_handler(handler)
    for handler in verif.get_handlers():   app.add_handler(handler)
    for handler in admin.get_handlers():   app.add_handler(handler)
    return app


async def main():
    logger.info("🚀 Starting Stripe Verif Bot (Firebase)...")
    await init_db()
    logger.info("✅ Firebase Firestore connected")

    app = build_application()
    scheduler = setup_scheduler(app)
    scheduler.start()
    logger.info("✅ Scheduler started")
    logger.info("✅ Bot polling started")
    await app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
