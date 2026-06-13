"""
bot/sqlite_db.py — SQLite Local Database queries fallback
"""
import os
import sqlite3
import json
from datetime import datetime
from loguru import logger

DB_PATH = "data/backup.db"

def sqlite_init_db():
    dir_name = os.path.dirname(DB_PATH)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        role TEXT,
        is_active INTEGER DEFAULT 1,
        joined_at TEXT,
        approved_by INTEGER,
        email TEXT,
        firebase_uid TEXT,
        password_hash TEXT
    )""")
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    except sqlite3.OperationalError:
        pass
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        title TEXT,
        description TEXT,
        sheet_tab TEXT,
        quota_total INTEGER DEFAULT 0,
        quota_per_staff INTEGER DEFAULT 0,
        deadline TEXT,
        repeat_type TEXT DEFAULT 'daily',
        assigned_to TEXT DEFAULT '["all"]',
        status TEXT DEFAULT 'active',
        created_by INTEGER,
        created_at TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sheet_urls (
        id TEXT PRIMARY KEY,
        task_id TEXT,
        date TEXT,
        account TEXT,
        api_key TEXT,
        api_key_status TEXT,
        payment_url TEXT,
        notes TEXT,
        status TEXT DEFAULT 'PENDING',
        http_code INTEGER,
        error_msg TEXT,
        assigned_to TEXT,
        verified_by TEXT,
        verified_at TEXT,
        created_at TEXT,
        assigned_at TEXT
    )""")

    # Upgrade existing database if columns are missing
    try:
        cursor.execute("ALTER TABLE sheet_urls ADD COLUMN api_key TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE sheet_urls ADD COLUMN api_key_status TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE sheet_urls ADD COLUMN assigned_to TEXT")
    except Exception:
        pass
    # Migrasi: isi assigned_to dari verified_by untuk data lama
    try:
        cursor.execute("UPDATE sheet_urls SET assigned_to = verified_by WHERE assigned_to IS NULL AND verified_by IS NOT NULL")
    except Exception:
        pass
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_progress (
        id TEXT PRIMARY KEY,
        task_id TEXT,
        user_id INTEGER,
        date TEXT,
        submitted INTEGER DEFAULT 0,
        verified_ok INTEGER DEFAULT 0,
        verified_fail INTEGER DEFAULT 0,
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
    conn.commit()
    conn.close()
    logger.info("[SQLite] Database initialized/verified.")


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    # Convert is_active to boolean
    if "is_active" in d:
        d["is_active"] = bool(d["is_active"])
    # Parse JSON for assigned_to (hanya untuk tabel tasks yang menyimpan JSON array)
    if "assigned_to" in d and d["assigned_to"]:
        try:
            if isinstance(d["assigned_to"], str) and d["assigned_to"].startswith("["):
                d["assigned_to"] = json.loads(d["assigned_to"])
        except Exception:
            pass
    return d


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    return conn


def sqlite_get_user(user_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def sqlite_get_user_by_username(username: str) -> dict | None:
    if not username:
        return None
    clean_username = username.lstrip("@").strip()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? OR username = ?", (username, clean_username))
    row = cursor.fetchone()
    conn.close()
    return row


def sqlite_create_user(user_id: int, username: str, full_name: str, role: str = "pending") -> dict:
    from bot.config import TZ
    joined_at = datetime.now(TZ).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO users (user_id, username, full_name, role, is_active, joined_at, approved_by)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, username, full_name, role, 1, joined_at, None))
    conn.commit()
    conn.close()
    return {
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "role": role,
        "is_active": True,
        "joined_at": joined_at,
        "approved_by": None
    }


def sqlite_update_user(user_id: int, **kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    if kwargs:
        keys = list(kwargs.keys())
        values = list(kwargs.values())
        # Convert bool to int for sqlite
        for i, val in enumerate(values):
            if isinstance(val, bool):
                values[i] = 1 if val else 0
        set_clause = ", ".join([f"{k} = ?" for k in keys])
        values.append(user_id)
        cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", tuple(values))
        conn.commit()
    conn.close()


def sqlite_list_users(role: str | None = None) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    if role:
        cursor.execute("SELECT * FROM users WHERE role = ?", (role,))
    else:
        cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    conn.close()
    return rows


def sqlite_get_task(task_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    if row and "task_id" in row and "id" not in row:
        row = dict(row)
        row["id"] = row["task_id"]
    return row


def sqlite_create_task(task_data: dict) -> dict:
    from bot.config import TZ
    created_at = datetime.now(TZ).isoformat()
    task_data["created_at"] = created_at
    assigned_to = task_data.get("assigned_to", '["all"]')
    if isinstance(assigned_to, list):
        assigned_to = json.dumps(assigned_to)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO tasks (task_id, title, description, sheet_tab, quota_total, quota_per_staff, deadline, repeat_type, assigned_to, status, created_by, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        task_data.get("task_id"),
        task_data.get("title"),
        task_data.get("description"),
        task_data.get("sheet_tab"),
        task_data.get("quota_total", 0),
        task_data.get("quota_per_staff", 0),
        task_data.get("deadline"),
        task_data.get("repeat_type", "daily"),
        assigned_to,
        task_data.get("status", "active"),
        task_data.get("created_by"),
        created_at
    ))
    conn.commit()
    conn.close()
    return task_data


def sqlite_update_task(task_id: str, **kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    if kwargs:
        keys = list(kwargs.keys())
        values = list(kwargs.values())
        for i, val in enumerate(values):
            if isinstance(val, bool):
                values[i] = 1 if val else 0
            elif isinstance(val, list):
                values[i] = json.dumps(val)
        set_clause = ", ".join([f"{k} = ?" for k in keys])
        values.append(task_id)
        cursor.execute(f"UPDATE tasks SET {set_clause} WHERE task_id = ?", tuple(values))
        conn.commit()
    conn.close()


def sqlite_list_tasks(status: str | None = "active") -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("SELECT * FROM tasks WHERE status = ?", (status,))
    else:
        cursor.execute("SELECT * FROM tasks")
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        row = dict(r)
        if "task_id" in row and "id" not in row:
            row["id"] = row["task_id"]
        results.append(row)
    return results


def sqlite_add_sheet_url(task_id: str, date: str, account: str,
                         payment_url: str, notes: str, api_key: str = "", check_exists: bool = True) -> str:
    from bot.config import TZ
    import hashlib
    doc_id = hashlib.md5(f"{task_id}_{payment_url}".encode("utf-8")).hexdigest()
    created_at = datetime.now(TZ).isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    if check_exists:
        cursor.execute("SELECT 1 FROM sheet_urls WHERE id = ?", (doc_id,))
        if cursor.fetchone():
            conn.close()
            return doc_id

    cursor.execute("""
    INSERT OR REPLACE INTO sheet_urls (id, task_id, date, account, api_key, payment_url, notes, status, http_code, error_msg, verified_by, verified_at, created_at, assigned_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        doc_id, task_id, date, account, api_key, payment_url, notes, "PENDING", None, None, None, None, created_at, None
    ))
    conn.commit()
    conn.close()
    return doc_id


def sqlite_get_sheet_url(doc_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sheet_urls WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def sqlite_update_sheet_url(doc_id: str, **kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    if kwargs:
        keys = list(kwargs.keys())
        values = list(kwargs.values())
        set_clause = ", ".join([f"{k} = ?" for k in keys])
        values.append(doc_id)
        cursor.execute(f"UPDATE sheet_urls SET {set_clause} WHERE id = ?", tuple(values))
        conn.commit()
    conn.close()


def sqlite_count_sheet_urls(task_id: str, date: str, status: str | None = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("""
        SELECT COUNT(*) as count FROM sheet_urls 
        WHERE task_id = ? AND date = ? AND status = ?
        """, (task_id, date, status))
    else:
        cursor.execute("""
        SELECT COUNT(*) as count FROM sheet_urls 
        WHERE task_id = ? AND date = ?
        """, (task_id, date))
    row = cursor.fetchone()
    conn.close()
    return row["count"] if row else 0


def sqlite_get_next_pending_url(task_id: str, date: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM sheet_urls 
    WHERE task_id = ? AND date = ? AND status = 'PENDING'
    LIMIT 1
    """, (task_id, date))
    row = cursor.fetchone()
    conn.close()
    return row

def sqlite_ensure_quota_synced(task_id: str, date_str: str, user_id: int) -> list[dict]:
    """
    Pastikan jumlah URL yang ter-reserve untuk user ini sesuai dengan quota_per_staff terbaru.
    Jika quota naik, otomatis assign URL tambahan dari pool.
    Return: list URL yang BARU di-assign (list kosong jika tidak ada perubahan).
    """
    user_id_str = str(user_id)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT quota_per_staff FROM tasks WHERE task_id = ?", (task_id,))
    task_row = cursor.fetchone()
    quota_staff = task_row["quota_per_staff"] if task_row else 0

    if quota_staff <= 0:
        conn.close()
        return []

    cursor.execute("SELECT submitted FROM task_progress WHERE id = ?",
                   (f"{task_id}_{user_id}_{date_str}",))
    prog_row = cursor.fetchone()
    submitted = prog_row["submitted"] if prog_row else 0

    cursor.execute("""
    SELECT COUNT(*) as count FROM sheet_urls
    WHERE task_id = ? AND date = ? AND status IN ('PENDING','PROCESSING') AND verified_by = ?
    """, (task_id, date_str, user_id_str))
    total_reserved = cursor.fetchone()["count"]

    already_counted = submitted + total_reserved
    gap = max(0, quota_staff - already_counted)

    if gap > 0:
        cursor.execute("""
        SELECT * FROM sheet_urls
        WHERE task_id = ? AND date = ? AND status = 'PENDING' AND (verified_by IS NULL OR verified_by = '')
        ORDER BY created_at ASC, id ASC
        LIMIT ?
        """, (task_id, date_str, gap))
        extras = cursor.fetchall()
        for r in extras:
            cursor.execute("UPDATE sheet_urls SET verified_by = ? WHERE id = ?",
                           (user_id_str, r["id"]))
        if extras:
            conn.commit()
        conn.close()
        return extras

    conn.close()
    return []


def sqlite_get_or_claim_next_url(task_id: str, date_str: str, user_id: int) -> tuple[dict | None, list[dict]]:
    from bot.config import TZ
    from datetime import datetime, timedelta
    now = datetime.now(TZ)
    user_id_str = str(user_id)

    conn = get_connection()
    cursor = conn.cursor()

    # 1. Cek PROCESSING
    cursor.execute("""
    SELECT * FROM sheet_urls 
    WHERE task_id = ? AND date = ? AND status = 'PROCESSING' AND verified_by = ?
    LIMIT 1
    """, (task_id, date_str, user_id_str))
    row = cursor.fetchone()
    if row:
        conn.close()
        return row, []

    # 2. Cek apakah user punya PENDING yang sudah di-assign ke dia
    cursor.execute("""
    SELECT * FROM sheet_urls
    WHERE task_id = ? AND date = ? AND status = 'PENDING' AND verified_by = ?
    ORDER BY created_at ASC, id ASC
    LIMIT 1
    """, (task_id, date_str, user_id_str))
    row_to_claim = cursor.fetchone()

    if row_to_claim:
        # Update status menjadi PROCESSING
        cursor.execute("""
        UPDATE sheet_urls 
        SET status = 'PROCESSING', assigned_at = ?
        WHERE id = ?
        """, (now.isoformat(), row_to_claim["id"]))
        conn.commit()

        row_to_claim["status"] = "PROCESSING"
        row_to_claim["assigned_at"] = now.isoformat()
        conn.close()
        return row_to_claim, []

    # Ambil quota terbaru dari DB
    cursor.execute("SELECT quota_per_staff FROM tasks WHERE task_id = ?", (task_id,))
    task_row = cursor.fetchone()
    quota_staff = task_row["quota_per_staff"] if task_row else 0

    # Hitung total URL yang sudah ter-reserve untuk user ini
    cursor.execute("""
    SELECT COUNT(*) as count FROM sheet_urls
    WHERE task_id = ? AND date = ? AND status IN ('PENDING', 'PROCESSING') AND verified_by = ?
    """, (task_id, date_str, user_id_str))
    total_reserved = cursor.fetchone()["count"]

    # Cek progress submit
    cursor.execute("SELECT submitted FROM task_progress WHERE id = ?",
                   (f"{task_id}_{user_id}_{date_str}",))
    prog_row = cursor.fetchone()
    submitted = prog_row["submitted"] if prog_row else 0

    # Jika quota naik, tambahkan slot baru dari pool ke user ini
    if quota_staff > 0:
        already_counted = submitted + total_reserved
        remaining_quota = max(0, quota_staff - already_counted)
        if remaining_quota > 0:
            cursor.execute("""
            SELECT * FROM sheet_urls
            WHERE task_id = ? AND date = ? AND status = 'PENDING' AND (verified_by IS NULL OR verified_by = '')
            ORDER BY created_at ASC, id ASC
            LIMIT ?
            """, (task_id, date_str, remaining_quota))
            extra_rows = cursor.fetchall()
            for r in extra_rows:
                cursor.execute("UPDATE sheet_urls SET verified_by = ? WHERE id = ?",
                               (user_id_str, r["id"]))
            if extra_rows:
                conn.commit()

    # 2. Cek apakah user punya PENDING yang sudah di-assign ke dia (termasuk yang baru ditambah)
    cursor.execute("""
    SELECT * FROM sheet_urls
    WHERE task_id = ? AND date = ? AND status = 'PENDING' AND verified_by = ?
    ORDER BY created_at ASC, id ASC
    LIMIT 1
    """, (task_id, date_str, user_id_str))
    row_to_claim = cursor.fetchone()

    if row_to_claim:
        cursor.execute("""
        UPDATE sheet_urls
        SET status = 'PROCESSING', assigned_at = ?
        WHERE id = ?
        """, (now.isoformat(), row_to_claim["id"]))
        conn.commit()

        row_to_claim["status"] = "PROCESSING"
        row_to_claim["assigned_at"] = now.isoformat()
        conn.close()
        return row_to_claim, []

    # 3. Claim fresh block jika belum ada reserved
    if quota_staff > 0:
        remaining = max(0, quota_staff - submitted - total_reserved)
        if remaining <= 0:
            conn.close()
            return None, []
        block_size = remaining
    else:
        block_size = 20

    cursor.execute("""
    SELECT * FROM sheet_urls
    WHERE task_id = ? AND date = ? AND status = 'PENDING' AND (verified_by IS NULL OR verified_by = '')
    ORDER BY created_at ASC, id ASC
    LIMIT ?
    """, (task_id, date_str, block_size))
    rows = cursor.fetchall()

    if rows:
        # Baris pertama langsung kita klaim sebagai PROCESSING
        first_row = rows[0]
        cursor.execute("""
        UPDATE sheet_urls
        SET status = 'PROCESSING', verified_by = ?, assigned_at = ?
        WHERE id = ?
        """, (user_id_str, now.isoformat(), first_row["id"]))

        # Sisa baris kita tandai verified_by = user_id_str agar ter-reserve untuk user ini
        for r in rows[1:]:
            cursor.execute("""
            UPDATE sheet_urls
            SET verified_by = ?
            WHERE id = ?
            """, (user_id_str, r["id"]))

        conn.commit()

        first_row["status"] = "PROCESSING"
        first_row["verified_by"] = user_id_str
        first_row["assigned_at"] = now.isoformat()
        conn.close()
        return first_row, rows

    # 4. Cari PROCESSING ditinggal > 5 menit jika tidak ada pending sama sekali
    five_min_ago = (now - timedelta(minutes=5)).isoformat()
    cursor.execute("""
    SELECT * FROM sheet_urls 
    WHERE task_id = ? AND date = ? AND status = 'PROCESSING' AND assigned_at < ?
    ORDER BY created_at ASC, id ASC
    LIMIT 1
    """, (task_id, date_str, five_min_ago))
    row_to_claim = cursor.fetchone()

    if row_to_claim:
        cursor.execute("""
        UPDATE sheet_urls 
        SET status = 'PROCESSING', verified_by = ?, assigned_at = ?
        WHERE id = ?
        """, (user_id_str, now.isoformat(), row_to_claim["id"]))
        conn.commit()

        row_to_claim["status"] = "PROCESSING"
        row_to_claim["verified_by"] = user_id_str
        row_to_claim["assigned_at"] = now.isoformat()
        conn.close()
        return row_to_claim, []

    conn.close()
    return None, []


def sqlite_list_sheet_urls(task_id: str | None = None, date: str | None = None,
                           status: str | None = None, limit: int = 50,
                           offset: int = 0, verified_by: str | None = None) -> tuple[list[dict], int]:
    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []
    if task_id:
        where_clauses.append("task_id = ?")
        params.append(task_id)
    if date:
        where_clauses.append("date = ?")
        params.append(date)
    if status:
        where_clauses.append("status = ?")
        params.append(status)
    if verified_by:
        where_clauses.append("verified_by = ?")
        params.append(str(verified_by))

    where_str = ""
    if where_clauses:
        where_str = "WHERE " + " AND ".join(where_clauses)

    # Count total
    cursor.execute(f"SELECT COUNT(*) as count FROM sheet_urls {where_str}", tuple(params))
    total = cursor.fetchone()["count"]

    # Select limited/offsetted rows
    select_query = f"SELECT * FROM sheet_urls {where_str} ORDER BY created_at ASC, id ASC LIMIT ? OFFSET ?"
    select_params = list(params)
    select_params.extend([limit, offset])
    cursor.execute(select_query, tuple(select_params))
    rows = cursor.fetchall()
    conn.close()
    return rows, total


def sqlite_get_progress(task_id: str, user_id: int, date: str) -> dict | None:
    doc_id = f"{task_id}_{user_id}_{date}"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM task_progress WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def sqlite_upsert_progress(task_id: str, user_id: int, date: str,
                           submitted_delta: int = 0, ok_delta: int = 0,
                           fail_delta: int = 0):
    doc_id = f"{task_id}_{user_id}_{date}"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM task_progress WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    if row:
        cursor.execute("""
        UPDATE task_progress 
        SET submitted = submitted + ?, verified_ok = verified_ok + ?, verified_fail = verified_fail + ?
        WHERE id = ?
        """, (submitted_delta, ok_delta, fail_delta, doc_id))
    else:
        cursor.execute("""
        INSERT INTO task_progress (id, task_id, user_id, date, submitted, verified_ok, verified_fail)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (doc_id, task_id, user_id, date, submitted_delta, ok_delta, fail_delta))
    conn.commit()
    conn.close()


def sqlite_list_progress_by_date(date: str) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM task_progress WHERE date = ?", (date,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def sqlite_list_progress_by_user(user_id: int, limit: int = 21) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM task_progress WHERE user_id = ?
    ORDER BY date DESC LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows


def sqlite_add_audit_log(actor_id: int, action: str, target_type: str,
                         target_id: str, detail: dict | None = None):
    from bot.config import TZ
    import uuid
    doc_id = str(uuid.uuid4())
    timestamp = datetime.now(TZ).isoformat()
    detail_str = json.dumps(detail or {})

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO audit_logs (id, actor_id, action, target_type, target_id, detail, timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (doc_id, actor_id, action, target_type, target_id, detail_str, timestamp))
    conn.commit()
    conn.close()


def sqlite_get_user_active_tasks_today(user_id: int, date_str: str) -> list[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT DISTINCT task_id FROM sheet_urls
    WHERE verified_by = ? AND date = ? AND status IN ('PROCESSING', 'PENDING')
    """, (str(user_id), date_str))
    rows = cursor.fetchall()
    conn.close()
    return [r["task_id"] for r in rows]


def sqlite_sync_task_assignments(task_id: str, date_str: str) -> list[dict]:
    task = sqlite_get_task(task_id)
    if not task:
        return []
    quota_staff = task.get("quota_per_staff", 0)
    if quota_staff <= 0:
        return []

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT verified_by FROM sheet_urls
        WHERE task_id = ? AND date = ? AND verified_by IS NOT NULL AND verified_by != ''
    """, (task_id, date_str))
    user_rows = cursor.fetchall()

    newly_assigned_urls = []

    for u_row in user_rows:
        user_id_str = u_row["verified_by"]
        if not user_id_str:
            continue

        cursor.execute("""
            SELECT COUNT(*) as count FROM sheet_urls
            WHERE task_id = ? AND date = ? AND verified_by = ?
        """, (task_id, date_str, user_id_str))
        total_assigned = cursor.fetchone()["count"]

        if total_assigned < quota_staff:
            needed = quota_staff - total_assigned
            
            cursor.execute("""
                SELECT * FROM sheet_urls
                WHERE task_id = ? AND date = ? AND status = 'PENDING' AND (verified_by IS NULL OR verified_by = '')
                ORDER BY created_at ASC, id ASC
                LIMIT ?
            """, (task_id, date_str, needed))
            pending_rows = cursor.fetchall()
            
            for r in pending_rows:
                cursor.execute("""
                    UPDATE sheet_urls
                    SET verified_by = ?
                    WHERE id = ?
                """, (user_id_str, r["id"]))
                newly_assigned_urls.append(r)

    conn.commit()
    conn.close()
    return newly_assigned_urls
