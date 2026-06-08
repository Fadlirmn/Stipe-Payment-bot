"""
bot/backup.py — Local SQLite Backup Service for PostgreSQL Data
Provides functions to backup PostgreSQL data to SQLite and restore from SQLite to PostgreSQL.
"""
from __future__ import annotations

import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from loguru import logger

# Get Postgres details from env
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB = os.getenv("POSTGRES_DB", "stripe_verif")
PG_USER = os.getenv("POSTGRES_USER", "postgres")
PG_PWD = os.getenv("POSTGRES_PASSWORD", "postgres")

def get_pg_connection():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PWD,
        cursor_factory=RealDictCursor
    )

async def backup_postgres_to_sqlite(db_path: str = "data/backup.db") -> tuple[bool, str]:
    """
    Membaca seluruh data dari PostgreSQL dan menyimpannya ke database SQLite lokal.
    """
    try:
        # Buat direktori data jika belum ada
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        sqlite_conn = sqlite3.connect(db_path)
        sqlite_cursor = sqlite_conn.cursor()

        # 1. Buat Tabel-tabel di SQLite
        sqlite_cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            role TEXT,
            is_active INTEGER,
            joined_at TEXT,
            approved_by INTEGER,
            email TEXT,
            firebase_uid TEXT,
            password_hash TEXT
        )""")

        sqlite_cursor.execute("""
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

        sqlite_cursor.execute("""
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

        sqlite_cursor.execute("""
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

        sqlite_cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            actor_id INTEGER,
            action TEXT,
            target_type TEXT,
            target_id TEXT,
            detail TEXT,
            timestamp TEXT
        )""")

        pg_conn = get_pg_connection()
        pg_cursor = pg_conn.cursor()

        # 2. Backup Users
        pg_cursor.execute("SELECT * FROM users")
        users = pg_cursor.fetchall()
        for u in users:
            sqlite_cursor.execute("""
            INSERT OR REPLACE INTO users (user_id, username, full_name, role, is_active, joined_at, approved_by, email, firebase_uid, password_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                u["user_id"], u["username"], u["full_name"], u["role"], u["is_active"],
                u["joined_at"], u["approved_by"], u["email"], u["firebase_uid"], u["password_hash"]
            ))

        # 3. Backup Tasks
        pg_cursor.execute("SELECT * FROM tasks")
        tasks = pg_cursor.fetchall()
        for t in tasks:
            sqlite_cursor.execute("""
            INSERT OR REPLACE INTO tasks (task_id, title, description, sheet_tab, quota_total, quota_per_staff, deadline, repeat_type, assigned_to, status, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t["task_id"], t["title"], t["description"], t["sheet_tab"], t["quota_total"],
                t["quota_per_staff"], t["deadline"], t["repeat_type"], t["assigned_to"], t["status"],
                t["created_by"], t["created_at"]
            ))

        # 4. Backup Sheet URLs
        pg_cursor.execute("SELECT * FROM sheet_urls")
        urls = pg_cursor.fetchall()
        for url in urls:
            sqlite_cursor.execute("""
            INSERT OR REPLACE INTO sheet_urls (id, task_id, date, account, payment_url, notes, status, http_code, error_msg, verified_by, verified_at, created_at, assigned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                url["id"], url["task_id"], url["date"], url["account"], url["payment_url"],
                url["notes"], url["status"], url["http_code"], url["error_msg"], url["verified_by"],
                url["verified_at"], url["created_at"], url["assigned_at"]
            ))

        # 5. Backup Task Progress
        pg_cursor.execute("SELECT * FROM task_progress")
        progs = pg_cursor.fetchall()
        for p in progs:
            sqlite_cursor.execute("""
            INSERT OR REPLACE INTO task_progress (id, task_id, user_id, date, submitted, verified_ok, verified_fail, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p["id"], p["task_id"], p["user_id"], p["date"], p["submitted"],
                p["verified_ok"], p["verified_fail"], p["completed_at"]
            ))

        # 6. Backup Audit Logs
        pg_cursor.execute("SELECT * FROM audit_logs")
        logs = pg_cursor.fetchall()
        for log in logs:
            sqlite_cursor.execute("""
            INSERT OR REPLACE INTO audit_logs (id, actor_id, action, target_type, target_id, detail, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                log["id"], log["actor_id"], log["action"], log["target_type"], log["target_id"],
                log["detail"], log["timestamp"]
            ))

        pg_cursor.close()
        pg_conn.close()

        sqlite_conn.commit()
        sqlite_conn.close()

        msg = (
            f"Backup sukses! "
            f"Users: {len(users)}, Tasks: {len(tasks)}, URLs: {len(urls)}, "
            f"Progress: {len(progs)}, Logs: {len(logs)}."
        )
        logger.info(f"[Backup] {msg}")
        return True, msg

    except Exception as e:
        err_msg = f"Gagal mencadangkan data ke SQLite: {e}"
        logger.error(f"[Backup] {err_msg}")
        return False, err_msg

async def restore_sqlite_to_postgres(db_path: str = "data/backup.db") -> tuple[bool, str]:
    """
    Membaca seluruh data dari database SQLite lokal dan memulihkannya ke PostgreSQL.
    """
    try:
        if not os.path.exists(db_path):
            return False, f"File database backup lokal tidak ditemukan di: {db_path}"

        sqlite_conn = sqlite3.connect(db_path)
        # Dictionary row factory
        def dict_factory(cursor, row):
            d = {}
            for idx, col in enumerate(cursor.description):
                d[col[0]] = row[idx]
            return d
        sqlite_conn.row_factory = dict_factory
        sqlite_cursor = sqlite_conn.cursor()

        pg_conn = get_pg_connection()
        pg_cursor = pg_conn.cursor()

        # 1. Restore Users
        sqlite_cursor.execute("SELECT * FROM users")
        users = sqlite_cursor.fetchall()
        for u in users:
            pg_cursor.execute("""
            INSERT INTO users (user_id, username, full_name, role, is_active, joined_at, approved_by, email, firebase_uid, password_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name,
                role = EXCLUDED.role,
                is_active = EXCLUDED.is_active,
                joined_at = EXCLUDED.joined_at,
                approved_by = EXCLUDED.approved_by,
                email = EXCLUDED.email,
                firebase_uid = EXCLUDED.firebase_uid,
                password_hash = EXCLUDED.password_hash
            """, (
                u["user_id"], u["username"], u["full_name"], u["role"], u["is_active"],
                u["joined_at"], u["approved_by"], u["email"], u["firebase_uid"], u["password_hash"]
            ))

        # 2. Restore Tasks
        sqlite_cursor.execute("SELECT * FROM tasks")
        tasks = sqlite_cursor.fetchall()
        for t in tasks:
            pg_cursor.execute("""
            INSERT INTO tasks (task_id, title, description, sheet_tab, quota_total, quota_per_staff, deadline, repeat_type, assigned_to, status, created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (task_id) DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                sheet_tab = EXCLUDED.sheet_tab,
                quota_total = EXCLUDED.quota_total,
                quota_per_staff = EXCLUDED.quota_per_staff,
                deadline = EXCLUDED.deadline,
                repeat_type = EXCLUDED.repeat_type,
                assigned_to = EXCLUDED.assigned_to,
                status = EXCLUDED.status,
                created_by = EXCLUDED.created_by,
                created_at = EXCLUDED.created_at
            """, (
                t["task_id"], t["title"], t["description"], t["sheet_tab"], t["quota_total"],
                t["quota_per_staff"], t["deadline"], t["repeat_type"], t["assigned_to"], t["status"],
                t["created_by"], t["created_at"]
            ))

        # 3. Restore Sheet URLs
        sqlite_cursor.execute("SELECT * FROM sheet_urls")
        urls = sqlite_cursor.fetchall()
        for url in urls:
            pg_cursor.execute("""
            INSERT INTO sheet_urls (id, task_id, date, account, payment_url, notes, status, http_code, error_msg, verified_by, verified_at, created_at, assigned_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                task_id = EXCLUDED.task_id,
                date = EXCLUDED.date,
                account = EXCLUDED.account,
                payment_url = EXCLUDED.payment_url,
                notes = EXCLUDED.notes,
                status = EXCLUDED.status,
                http_code = EXCLUDED.http_code,
                error_msg = EXCLUDED.error_msg,
                verified_by = EXCLUDED.verified_by,
                verified_at = EXCLUDED.verified_at,
                created_at = EXCLUDED.created_at,
                assigned_at = EXCLUDED.assigned_at
            """, (
                url["id"], url["task_id"], url["date"], url["account"], url["payment_url"],
                url["notes"], url["status"], url["http_code"], url["error_msg"], url["verified_by"],
                url["verified_at"], url["created_at"], url["assigned_at"]
            ))

        # 4. Restore Task Progress
        sqlite_cursor.execute("SELECT * FROM task_progress")
        progs = sqlite_cursor.fetchall()
        for p in progs:
            pg_cursor.execute("""
            INSERT INTO task_progress (id, task_id, user_id, date, submitted, verified_ok, verified_fail, completed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                task_id = EXCLUDED.task_id,
                user_id = EXCLUDED.user_id,
                date = EXCLUDED.date,
                submitted = EXCLUDED.submitted,
                verified_ok = EXCLUDED.verified_ok,
                verified_fail = EXCLUDED.verified_fail,
                completed_at = EXCLUDED.completed_at
            """, (
                p["id"], p["task_id"], p["user_id"], p["date"], p["submitted"],
                p["verified_ok"], p["verified_fail"], p["completed_at"]
            ))

        # 5. Restore Audit Logs
        sqlite_cursor.execute("SELECT * FROM audit_logs")
        logs = sqlite_cursor.fetchall()
        for log in logs:
            pg_cursor.execute("""
            INSERT INTO audit_logs (id, actor_id, action, target_type, target_id, detail, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                actor_id = EXCLUDED.actor_id,
                action = EXCLUDED.action,
                target_type = EXCLUDED.target_type,
                target_id = EXCLUDED.target_id,
                detail = EXCLUDED.detail,
                timestamp = EXCLUDED.timestamp
            """, (
                log["id"], log["actor_id"], log["action"], log["target_type"], log["target_id"],
                log["detail"], log["timestamp"]
            ))

        pg_conn.commit()
        pg_cursor.close()
        pg_conn.close()

        sqlite_cursor.close()
        sqlite_conn.close()

        msg = (
            f"Restore sukses! Dimasukkan ke PostgreSQL -> "
            f"Users: {len(users)}, Tasks: {len(tasks)}, URLs: {len(urls)}, "
            f"Progress: {len(progs)}, Logs: {len(logs)}."
        )
        logger.info(f"[Restore] {msg}")
        return True, msg

    except Exception as e:
        err_msg = f"Gagal memulihkan data dari SQLite ke PostgreSQL: {e}"
        logger.error(f"[Restore] {err_msg}")
        return False, err_msg
