"""
migrate_to_postgres.py — Tool to migrate data from Firebase Firestore (and/or SQLite) to PostgreSQL.
"""
from __future__ import annotations

import os
import sys
import json
import sqlite3
import asyncio
from loguru import logger

# Add current directory to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.postgres_db import (
    postgres_init_db,
    postgres_create_user,
    postgres_create_task,
    postgres_add_sheet_url,
    postgres_upsert_progress,
    postgres_add_audit_log,
    postgres_update_user,
    postgres_update_sheet_url
)

async def migrate_firestore_to_postgres():
    import firebase_admin
    from firebase_admin import credentials, firestore
    from bot.config import FIREBASE_CREDENTIALS_JSON, FIREBASE_PROJECT_ID
    
    logger.info("Initializing connection to Firestore...")
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_JSON)
        firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
    
    db = firestore.AsyncClient(project=FIREBASE_PROJECT_ID)
    
    # Initialize PG tables
    logger.info("Initializing PostgreSQL schema...")
    postgres_init_db()

    # 1. Migrate Users
    logger.info("Migrating Users from Firestore...")
    users_snap = await db.collection("users").get()
    logger.info(f"Found {len(users_snap)} users in Firestore.")
    for doc in users_snap:
        data = doc.to_dict()
        user_id = int(doc.id)
        postgres_create_user(
            user_id=user_id,
            username=data.get("username", ""),
            full_name=data.get("full_name", ""),
            role=data.get("role", "pending")
        )
        # Apply other fields (email, is_active, firebase_uid, password_hash)
        postgres_update_user(
            user_id=user_id,
            is_active=data.get("is_active", True),
            joined_at=data.get("joined_at"),
            approved_by=data.get("approved_by"),
            email=data.get("email"),
            firebase_uid=data.get("firebase_uid"),
            password_hash=data.get("password_hash")
        )

    # 2. Migrate Tasks
    logger.info("Migrating Tasks from Firestore...")
    tasks_snap = await db.collection("tasks").get()
    logger.info(f"Found {len(tasks_snap)} tasks in Firestore.")
    for doc in tasks_snap:
        data = doc.to_dict()
        data["task_id"] = doc.id
        postgres_create_task(data)

    # 3. Migrate Sheet URLs
    logger.info("Migrating Sheet URLs from Firestore...")
    urls_snap = await db.collection("sheet_urls").get()
    logger.info(f"Found {len(urls_snap)} URLs in Firestore.")
    for doc in urls_snap:
        data = doc.to_dict()
        doc_id = doc.id
        postgres_add_sheet_url(
            task_id=data.get("task_id"),
            date=data.get("date"),
            account=data.get("account"),
            payment_url=data.get("payment_url"),
            notes=data.get("notes", ""),
            check_exists=False
        )
        # Update other fields (status, http_code, error_msg, verified_by, verified_at, created_at, assigned_at)
        postgres_update_sheet_url(
            doc_id=doc_id,
            status=data.get("status", "PENDING"),
            http_code=data.get("http_code"),
            error_msg=data.get("error_msg"),
            verified_by=data.get("verified_by"),
            verified_at=data.get("verified_at"),
            created_at=data.get("created_at"),
            assigned_at=data.get("assigned_at")
        )

    # 4. Migrate Task Progress
    logger.info("Migrating Task Progress from Firestore...")
    progress_snap = await db.collection("task_progress").get()
    logger.info(f"Found {len(progress_snap)} progress entries in Firestore.")
    for doc in progress_snap:
        data = doc.to_dict()
        postgres_upsert_progress(
            task_id=data.get("task_id"),
            user_id=int(data.get("user_id")),
            date=data.get("date"),
            submitted_delta=data.get("submitted", 0),
            ok_delta=data.get("verified_ok", 0),
            fail_delta=data.get("verified_fail", 0)
        )

    # 5. Migrate Audit Logs
    logger.info("Migrating Audit Logs from Firestore...")
    audit_snap = await db.collection("audit_logs").get()
    logger.info(f"Found {len(audit_snap)} audit logs in Firestore.")
    for doc in audit_snap:
        data = doc.to_dict()
        postgres_add_audit_log(
            actor_id=data.get("actor_id"),
            action=data.get("action"),
            target_type=data.get("target_type"),
            target_id=data.get("target_id"),
            detail=data.get("detail")
        )

    logger.success("Migration from Firestore to PostgreSQL completed successfully!")


def migrate_sqlite_to_postgres():
    DB_PATH = "data/backup.db"
    if not os.path.exists(DB_PATH):
        logger.warning(f"Local SQLite database not found at {DB_PATH}. Skipping SQLite migration.")
        return

    logger.info("Initializing connection to SQLite...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Initialize PG tables
    logger.info("Initializing PostgreSQL schema...")
    postgres_init_db()

    # 1. Migrate Users
    logger.info("Migrating Users from SQLite...")
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    logger.info(f"Found {len(rows)} users in SQLite.")
    for row in rows:
        user_id = row["user_id"]
        postgres_create_user(
            user_id=user_id,
            username=row["username"],
            full_name=row["full_name"],
            role=row["role"]
        )
        postgres_update_user(
            user_id=user_id,
            is_active=row["is_active"],
            joined_at=row["joined_at"],
            approved_by=row["approved_by"],
            email=row["email"],
            firebase_uid=row["firebase_uid"],
            password_hash=row["password_hash"]
        )

    # 2. Migrate Tasks
    logger.info("Migrating Tasks from SQLite...")
    cursor.execute("SELECT * FROM tasks")
    rows = cursor.fetchall()
    logger.info(f"Found {len(rows)} tasks in SQLite.")
    for row in rows:
        task_data = dict(row)
        postgres_create_task(task_data)

    # 3. Migrate Sheet URLs
    logger.info("Migrating Sheet URLs from SQLite...")
    cursor.execute("SELECT * FROM sheet_urls")
    rows = cursor.fetchall()
    logger.info(f"Found {len(rows)} URLs in SQLite.")
    for row in rows:
        postgres_add_sheet_url(
            task_id=row["task_id"],
            date=row["date"],
            account=row["account"],
            payment_url=row["payment_url"],
            notes=row["notes"],
            check_exists=False
        )
        postgres_update_sheet_url(
            doc_id=row["id"],
            status=row["status"],
            http_code=row["http_code"],
            error_msg=row["error_msg"],
            verified_by=row["verified_by"],
            verified_at=row["verified_at"],
            created_at=row["created_at"],
            assigned_at=row["assigned_at"]
        )

    # 4. Migrate Task Progress
    logger.info("Migrating Task Progress from SQLite...")
    cursor.execute("SELECT * FROM task_progress")
    rows = cursor.fetchall()
    logger.info(f"Found {len(rows)} progress entries in SQLite.")
    for row in rows:
        postgres_upsert_progress(
            task_id=row["task_id"],
            user_id=row["user_id"],
            date=row["date"],
            submitted_delta=row["submitted"],
            ok_delta=row["verified_ok"],
            fail_delta=row["verified_fail"]
        )

    # 5. Migrate Audit Logs
    logger.info("Migrating Audit Logs from SQLite...")
    cursor.execute("SELECT * FROM audit_logs")
    rows = cursor.fetchall()
    logger.info(f"Found {len(rows)} audit logs in SQLite.")
    for row in rows:
        try:
            detail = json.loads(row["detail"])
        except Exception:
            detail = {}
        postgres_add_audit_log(
            actor_id=row["actor_id"],
            action=row["action"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            detail=detail
        )

    conn.close()
    logger.success("Migration from SQLite to PostgreSQL completed successfully!")


if __name__ == "__main__":
    print("=== Database Migration Tool ===")
    print("1. Migrate from Firebase Firestore to PostgreSQL")
    print("2. Migrate from Local SQLite to PostgreSQL")
    print("================================")
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        asyncio.run(migrate_firestore_to_postgres())
    elif choice == "2":
        migrate_sqlite_to_postgres()
    else:
        print("Invalid choice.")
