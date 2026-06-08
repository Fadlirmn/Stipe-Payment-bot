"""
bot/backup.py — SQLite Local Backup Service for Firestore Data
"""
import os
import sqlite3
import json
from loguru import logger
import bot.firebase_db as fdb

async def backup_firestore_to_sqlite(db_path: str = "data/backup.db") -> tuple[bool, str]:
    """
    Membaca seluruh data dari semua koleksi di Firestore
    dan menyimpannya (INSERT OR REPLACE) ke database SQLite lokal.
    """
    try:
        # Buat direktori data jika belum ada
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1. Buat Tabel-tabel
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            role TEXT,
            is_active INTEGER,
            joined_at TEXT,
            approved_by INTEGER,
            email TEXT,
            firebase_uid TEXT
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            sheet_tab TEXT,
            quota_total INTEGER,
            quota_per_staff INTEGER,
            deadline TEXT,
            repeat_type TEXT,
            assigned_to TEXT,
            status TEXT,
            created_by INTEGER,
            created_at TEXT
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sheet_urls (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            date TEXT,
            account TEXT,
            payment_url TEXT,
            notes TEXT,
            status TEXT,
            http_code INTEGER,
            error_msg TEXT,
            verified_by TEXT,
            verified_at TEXT,
            created_at TEXT,
            assigned_at TEXT
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_progress (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            user_id INTEGER,
            date TEXT,
            submitted INTEGER,
            verified_ok INTEGER,
            verified_fail INTEGER,
            completed_at TEXT
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            actor_id INTEGER,
            action TEXT,
            target_type TEXT,
            target_id TEXT,
            detail TEXT,
            timestamp TEXT
        )""")

        # 2. Sinkronisasi Data Users
        users_col = fdb.users_col()
        users_docs = await users_col.get()
        user_count = 0
        for doc in users_docs:
            data = doc.to_dict()
            cursor.execute("""
            INSERT OR REPLACE INTO users (user_id, username, full_name, role, is_active, joined_at, approved_by, email, firebase_uid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("user_id"),
                data.get("username"),
                data.get("full_name"),
                data.get("role"),
                1 if data.get("is_active", True) else 0,
                data.get("joined_at"),
                data.get("approved_by"),
                data.get("email"),
                data.get("firebase_uid")
            ))
            user_count += 1

        # 3. Sinkronisasi Data Tasks
        tasks_col = fdb.tasks_col()
        tasks_docs = await tasks_col.get()
        task_count = 0
        for doc in tasks_docs:
            data = doc.to_dict()
            assigned_to = data.get("assigned_to", '["all"]')
            if isinstance(assigned_to, list):
                assigned_to = json.dumps(assigned_to)
            cursor.execute("""
            INSERT OR REPLACE INTO tasks (task_id, title, description, sheet_tab, quota_total, quota_per_staff, deadline, repeat_type, assigned_to, status, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("task_id"),
                data.get("title"),
                data.get("description"),
                data.get("sheet_tab"),
                data.get("quota_total"),
                data.get("quota_per_staff"),
                data.get("deadline"),
                data.get("repeat_type"),
                assigned_to,
                data.get("status"),
                data.get("created_by"),
                data.get("created_at")
            ))
            task_count += 1

        # 4. Sinkronisasi Data Sheet URLs
        urls_col = fdb.sheet_urls_col()
        urls_docs = await urls_col.get()
        url_count = 0
        for doc in urls_docs:
            data = doc.to_dict()
            cursor.execute("""
            INSERT OR REPLACE INTO sheet_urls (id, task_id, date, account, payment_url, notes, status, http_code, error_msg, verified_by, verified_at, created_at, assigned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc.id,
                data.get("task_id"),
                data.get("date"),
                data.get("account"),
                data.get("payment_url"),
                data.get("notes"),
                data.get("status"),
                data.get("http_code"),
                data.get("error_msg"),
                data.get("verified_by"),
                data.get("verified_at"),
                data.get("created_at"),
                data.get("assigned_at")
            ))
            url_count += 1

        # 5. Sinkronisasi Data Task Progress
        prog_col = fdb.progress_col()
        prog_docs = await prog_col.get()
        prog_count = 0
        for doc in prog_docs:
            data = doc.to_dict()
            cursor.execute("""
            INSERT OR REPLACE INTO task_progress (id, task_id, user_id, date, submitted, verified_ok, verified_fail, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc.id,
                data.get("task_id"),
                data.get("user_id"),
                data.get("date"),
                data.get("submitted"),
                data.get("verified_ok"),
                data.get("verified_fail"),
                data.get("completed_at")
            ))
            prog_count += 1

        # 6. Sinkronisasi Data Audit Logs
        audit_col = fdb.audit_col()
        audit_docs = await audit_col.get()
        audit_count = 0
        for doc in audit_docs:
            data = doc.to_dict()
            detail = data.get("detail", "")
            if isinstance(detail, (dict, list)):
                detail = json.dumps(detail)
            cursor.execute("""
            INSERT OR REPLACE INTO audit_logs (id, actor_id, action, target_type, target_id, detail, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                doc.id,
                data.get("actor_id"),
                data.get("action"),
                data.get("target_type"),
                data.get("target_id"),
                detail,
                data.get("timestamp")
            ))
            audit_count += 1

        conn.commit()
        conn.close()

        msg = (
            f"Backup sukses! "
            f"Users: {user_count}, Tasks: {task_count}, URLs: {url_count}, "
            f"Progress: {prog_count}, Logs: {audit_count}."
        )
        logger.info(f"[Backup] {msg}")
        return True, msg

    except Exception as e:
        err_msg = f"Gagal mencadangkan data ke SQLite: {e}"
        logger.error(f"[Backup] {err_msg}")
        return False, err_msg
