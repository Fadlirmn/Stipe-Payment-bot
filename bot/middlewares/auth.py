"""
middlewares/auth.py — Role-based access guard (Firebase version)
"""
from __future__ import annotations

from functools import wraps
from typing import Callable

from telegram import Update
from telegram.ext import ContextTypes

from bot.firebase_db import get_user, create_user
from bot.config import DEV_IDS


async def get_or_create_user(update: Update) -> dict | None:
    tg_user = update.effective_user
    if not tg_user:
        return None

    user = await get_user(tg_user.id)
    if not user:
        role = "dev" if tg_user.id in DEV_IDS else "pending"
        user = await create_user(
            user_id=tg_user.id,
            username=tg_user.username or "",
            full_name=tg_user.full_name or "",
            role=role,
        )
    return user


def require_role(*roles: str):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = await get_or_create_user(update)
            if not user or user.get("role") not in roles:
                await update.effective_message.reply_text(
                    "🚫 *Akses ditolak.*\nAnda tidak memiliki izin untuk perintah ini.",
                    parse_mode="Markdown",
                )
                return
            if not user.get("is_active", True):
                await update.effective_message.reply_text(
                    "⛔ *Akun Anda dinonaktifkan.* Hubungi admin.",
                    parse_mode="Markdown",
                )
                return
            return await func(update, context)
        return wrapper
    return decorator


def require_approved(func: Callable):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = await get_or_create_user(update)
        if not user or user.get("role") == "pending":
            await update.effective_message.reply_text(
                "⏳ *Akun Anda belum disetujui.*\n"
                "Mohon tunggu approval dari Admin.",
                parse_mode="Markdown",
            )
            return
        return await func(update, context)
    return wrapper
