"""
bot/db.py — Async PostgreSQL Database Wrapper
Provides async wrappers for postgres_db.py functions.
"""
from __future__ import annotations

import asyncio
import bot.postgres_db as pgdb

async def init_db():
    return await asyncio.to_thread(pgdb.postgres_init_db)

async def get_user(user_id: int) -> dict | None:
    return await asyncio.to_thread(pgdb.postgres_get_user, user_id)

async def create_user(user_id: int, username: str, full_name: str, role: str = "pending") -> dict:
    return await asyncio.to_thread(pgdb.postgres_create_user, user_id, username, full_name, role)

async def update_user(user_id: int, **kwargs):
    return await asyncio.to_thread(pgdb.postgres_update_user, user_id, **kwargs)

async def list_users(role: str | None = None) -> list[dict]:
    return await asyncio.to_thread(pgdb.postgres_list_users, role)

async def get_task(task_id: str) -> dict | None:
    return await asyncio.to_thread(pgdb.postgres_get_task, task_id)

async def create_task(task_data: dict) -> dict:
    return await asyncio.to_thread(pgdb.postgres_create_task, task_data)

async def update_task(task_id: str, **kwargs):
    return await asyncio.to_thread(pgdb.postgres_update_task, task_id, **kwargs)

async def list_tasks(status: str | None = "active") -> list[dict]:
    return await asyncio.to_thread(pgdb.postgres_list_tasks, status)

async def add_sheet_url(task_id: str, date: str, account: str, payment_url: str, notes: str, api_key: str = "", check_exists: bool = True) -> str:
    return await asyncio.to_thread(pgdb.postgres_add_sheet_url, task_id, date, account, payment_url, notes, api_key, check_exists)

async def get_sheet_url(doc_id: str) -> dict | None:
    return await asyncio.to_thread(pgdb.postgres_get_sheet_url, doc_id)

async def update_sheet_url(doc_id: str, **kwargs):
    return await asyncio.to_thread(pgdb.postgres_update_sheet_url, doc_id, **kwargs)

async def count_sheet_urls(task_id: str, date: str, status: str | None = None) -> int:
    return await asyncio.to_thread(pgdb.postgres_count_sheet_urls, task_id, date, status)

async def get_next_pending_url(task_id: str, date: str) -> dict | None:
    return await asyncio.to_thread(pgdb.postgres_get_next_pending_url, task_id, date)

async def get_or_claim_next_url(task_id: str, date_str: str, user_id: int) -> tuple[dict | None, list[dict]]:
    return await asyncio.to_thread(pgdb.postgres_get_or_claim_next_url, task_id, date_str, user_id)

async def list_sheet_urls(task_id: str | None = None, date: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0, verified_by: str | None = None) -> tuple[list[dict], int]:
    return await asyncio.to_thread(pgdb.postgres_list_sheet_urls, task_id, date, status, limit, offset, verified_by)

async def get_progress(task_id: str, user_id: int, date: str) -> dict | None:
    return await asyncio.to_thread(pgdb.postgres_get_progress, task_id, user_id, date)

async def upsert_progress(task_id: str, user_id: int, date: str, submitted_delta: int = 0, ok_delta: int = 0, fail_delta: int = 0):
    return await asyncio.to_thread(pgdb.postgres_upsert_progress, task_id, user_id, date, submitted_delta, ok_delta, fail_delta)

async def list_progress_by_date(date: str) -> list[dict]:
    return await asyncio.to_thread(pgdb.postgres_list_progress_by_date, date)

async def list_progress_by_user(user_id: int, limit: int = 21) -> list[dict]:
    return await asyncio.to_thread(pgdb.postgres_list_progress_by_user, user_id, limit)

async def add_audit_log(actor_id: int, action: str, target_type: str, target_id: str, detail: dict | None = None):
    return await asyncio.to_thread(pgdb.postgres_add_audit_log, actor_id, action, target_type, target_id, detail)

async def get_user_active_tasks_today(user_id: int, date_str: str) -> list[str]:
    return await asyncio.to_thread(pgdb.postgres_get_user_active_tasks_today, user_id, date_str)

async def reset_today(date_str: str) -> tuple[int, int]:
    return await asyncio.to_thread(pgdb.postgres_reset_today, date_str)

async def retry_failed_urls(date_str: str) -> int:
    return await asyncio.to_thread(pgdb.postgres_retry_failed_urls, date_str)

async def get_all_failed_urls() -> list[dict]:
    return await asyncio.to_thread(pgdb.postgres_get_all_failed_urls)

async def sync_task_assignments(task_id: str, date_str: str) -> list[dict]:
    return await asyncio.to_thread(pgdb.postgres_sync_task_assignments, task_id, date_str)

async def ensure_quota_synced(task_id: str, date_str: str, user_id: int) -> int:
    """Pastikan reserved block user sesuai quota terbaru. Return jumlah URL ter-assign."""
    return await asyncio.to_thread(pgdb.postgres_ensure_quota_synced, task_id, date_str, user_id)
