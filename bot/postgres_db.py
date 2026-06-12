"""
bot/postgres_db.py — PostgreSQL Local/Cloud Database queries fallback
"""
import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from datetime import datetime
from loguru import logger

PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB = os.getenv("POSTGRES_DB", "stripe_verif")
PG_USER = os.getenv("POSTGRES_USER", "postgres")
PG_PWD = os.getenv("POSTGRES_PASSWORD", "postgres")

def postgres_init_db():
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PWD
    )
    cursor = conn.cursor()
    
    # 1. users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        role TEXT,
        is_active INTEGER DEFAULT 1,
        joined_at TEXT,
        approved_by BIGINT,
        email TEXT,
        firebase_uid TEXT,
        password_hash TEXT
    )""")
    
    # 2. tasks table
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
        created_by BIGINT,
        created_at TEXT
    )""")
    
    # 3. sheet_urls table
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
        verified_by TEXT,
        verified_at TEXT,
        created_at TEXT,
        assigned_at TEXT
    )""")

    # Upgrade existing database if columns are missing
    try:
        cursor.execute("ALTER TABLE sheet_urls ADD COLUMN api_key TEXT")
    except Exception:
        conn.rollback()
    try:
        cursor.execute("ALTER TABLE sheet_urls ADD COLUMN api_key_status TEXT")
    except Exception:
        conn.rollback()
    
    # 4. task_progress table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_progress (
        id TEXT PRIMARY KEY,
        task_id TEXT,
        user_id BIGINT,
        date TEXT,
        submitted INTEGER DEFAULT 0,
        verified_ok INTEGER DEFAULT 0,
        verified_fail INTEGER DEFAULT 0,
        completed_at TEXT
    )""")
    
    # 5. audit_logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        actor_id BIGINT,
        action TEXT,
        target_type TEXT,
        target_id TEXT,
        detail TEXT,
        timestamp TEXT
    )""")
    
    # 6. Indexes for query and claim performance optimization
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sheet_urls_task_date_status ON sheet_urls (task_id, date, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sheet_urls_verified_by ON sheet_urls (verified_by)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sheet_urls_url ON sheet_urls (payment_url)")
    
    conn.commit()
    cursor.close()
    conn.close()
    logger.info("[PostgreSQL] Database initialized/verified.")


class PooledConnectionWrapper:
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        
    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)
        
    def commit(self):
        return self._conn.commit()
        
    def rollback(self):
        return self._conn.rollback()
        
    def close(self):
        if self._pool and self._conn:
            try:
                self._pool.putconn(self._conn)
            except Exception as e:
                logger.warning(f"[PostgreSQL] Failed to return connection to pool: {e}")
            self._conn = None
            self._pool = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)

# Initialize PostgreSQL Connection Pool globally
connection_pool = None
try:
    min_conn = int(os.getenv("PG_POOL_MIN", "5"))
    max_conn = int(os.getenv("PG_POOL_MAX", "50"))
    connection_pool = ThreadedConnectionPool(
        minconn=min_conn,
        maxconn=max_conn,
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PWD,
        cursor_factory=RealDictCursor
    )
    logger.info(f"[PostgreSQL] Threaded Connection Pool initialized with {min_conn}-{max_conn} connections.")
except Exception as e:
    logger.error(f"[PostgreSQL] Failed to initialize Threaded Connection Pool: {e}")

def get_connection():
    if connection_pool:
        try:
            conn = connection_pool.getconn()
            return PooledConnectionWrapper(conn, connection_pool)
        except Exception as e:
            logger.warning(f"[PostgreSQL] Connection pool exhausted or failed, falling back to new connection: {e}")
            
    # Fallback to direct connection if pool fails
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PWD,
        cursor_factory=RealDictCursor
    )
    return conn


def dict_clean(d):
    if d is None:
        return None
    res = dict(d)
    if "is_active" in res:
        res["is_active"] = bool(res["is_active"])
    if "assigned_to" in res and res["assigned_to"]:
        try:
            if isinstance(res["assigned_to"], str):
                res["assigned_to"] = json.loads(res["assigned_to"])
        except Exception:
            pass
    return res


def postgres_get_user(user_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict_clean(row)


def postgres_create_user(user_id: int, username: str, full_name: str, role: str = "pending") -> dict:
    from bot.config import TZ
    joined_at = datetime.now(TZ).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO users (user_id, username, full_name, role, is_active, joined_at, approved_by)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (user_id) DO UPDATE SET 
        username = EXCLUDED.username,
        full_name = EXCLUDED.full_name,
        role = EXCLUDED.role
    """, (user_id, username, full_name, role, 1, joined_at, None))
    conn.commit()
    cursor.close()
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


def postgres_update_user(user_id: int, **kwargs):
    if not kwargs:
        return
    conn = get_connection()
    cursor = conn.cursor()
    keys = list(kwargs.keys())
    values = list(kwargs.values())
    
    for i, val in enumerate(values):
        if isinstance(val, bool):
            values[i] = 1 if val else 0
            
    set_clause = ", ".join([f"{k} = %s" for k in keys])
    values.append(user_id)
    cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id = %s", tuple(values))
    conn.commit()
    cursor.close()
    conn.close()


def postgres_list_users(role: str | None = None) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    if role:
        cursor.execute("SELECT * FROM users WHERE role = %s", (role,))
    else:
        cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict_clean(r) for r in rows]


def postgres_get_task(task_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE task_id = %s", (task_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict_clean(row)


def postgres_create_task(task_data: dict) -> dict:
    from bot.config import TZ
    created_at = datetime.now(TZ).isoformat()
    task_data["created_at"] = created_at
    assigned_to = task_data.get("assigned_to", '["all"]')
    if isinstance(assigned_to, list):
        assigned_to = json.dumps(assigned_to)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
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
        status = EXCLUDED.status
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
    cursor.close()
    conn.close()
    return task_data


def postgres_update_task(task_id: str, **kwargs):
    if not kwargs:
        return
    conn = get_connection()
    cursor = conn.cursor()
    keys = list(kwargs.keys())
    values = list(kwargs.values())
    for i, val in enumerate(values):
        if isinstance(val, bool):
            values[i] = 1 if val else 0
        elif isinstance(val, list):
            values[i] = json.dumps(val)
    set_clause = ", ".join([f"{k} = %s" for k in keys])
    values.append(task_id)
    cursor.execute(f"UPDATE tasks SET {set_clause} WHERE task_id = %s", tuple(values))
    conn.commit()
    cursor.close()
    conn.close()


def postgres_list_tasks(status: str | None = "active") -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("SELECT * FROM tasks WHERE status = %s", (status,))
    else:
        cursor.execute("SELECT * FROM tasks")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict_clean(r) for r in rows]


def postgres_add_sheet_url(task_id: str, date: str, account: str,
                         payment_url: str, notes: str, api_key: str = "", check_exists: bool = True) -> str:
    from bot.config import TZ
    import hashlib
    doc_id = hashlib.md5(f"{task_id}_{payment_url}".encode("utf-8")).hexdigest()
    created_at = datetime.now(TZ).isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    if check_exists:
        cursor.execute("SELECT 1 FROM sheet_urls WHERE id = %s", (doc_id,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return doc_id

    cursor.execute("""
    INSERT INTO sheet_urls (id, task_id, date, account, api_key, payment_url, notes, status, http_code, error_msg, verified_by, verified_at, created_at, assigned_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id) DO NOTHING
    """, (
        doc_id, task_id, date, account, api_key, payment_url, notes, "PENDING", None, None, None, None, created_at, None
    ))
    conn.commit()
    cursor.close()
    conn.close()
    return doc_id


def postgres_get_sheet_url(doc_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sheet_urls WHERE id = %s", (doc_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict_clean(row)


def postgres_update_sheet_url(doc_id: str, **kwargs):
    if not kwargs:
        return
    conn = get_connection()
    cursor = conn.cursor()
    keys = list(kwargs.keys())
    values = list(kwargs.values())
    set_clause = ", ".join([f"{k} = %s" for k in keys])
    values.append(doc_id)
    cursor.execute(f"UPDATE sheet_urls SET {set_clause} WHERE id = %s", tuple(values))
    conn.commit()
    cursor.close()
    conn.close()


def postgres_count_sheet_urls(task_id: str, date: str, status: str | None = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("""
        SELECT COUNT(*) as count FROM sheet_urls 
        WHERE task_id = %s AND date = %s AND status = %s
        """, (task_id, date, status))
    else:
        cursor.execute("""
        SELECT COUNT(*) as count FROM sheet_urls 
        WHERE task_id = %s AND date = %s
        """, (task_id, date))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row["count"] if row else 0


def postgres_get_next_pending_url(task_id: str, date: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM sheet_urls 
    WHERE task_id = %s AND date = %s AND status = 'PENDING'
    LIMIT 1
    """, (task_id, date))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict_clean(row)


def postgres_ensure_quota_synced(task_id: str, date_str: str, user_id: int) -> int:
    """
    Pastikan jumlah URL yang ter-reserve untuk user ini sesuai dengan quota_per_staff terbaru.
    Jika quota naik, otomatis assign URL tambahan dari pool.
    Return: jumlah URL yang ter-assign setelah sync (PENDING + PROCESSING milik user).
    """
    user_id_str = str(user_id)
    conn = get_connection()
    cursor = conn.cursor()

    # Ambil quota terbaru
    cursor.execute("SELECT quota_per_staff FROM tasks WHERE task_id = %s", (task_id,))
    task_row = cursor.fetchone()
    quota_staff = task_row["quota_per_staff"] if task_row else 0

    if quota_staff <= 0:
        # Tidak ada quota limit — tidak perlu sync
        cursor.execute("""
        SELECT COUNT(*) as count FROM sheet_urls
        WHERE task_id = %s AND date = %s AND verified_by = %s AND status IN ('PENDING','PROCESSING')
        """, (task_id, date_str, user_id_str))
        total = cursor.fetchone()["count"]
        cursor.close()
        conn.close()
        return total

    # Hitung submitted
    cursor.execute("SELECT submitted FROM task_progress WHERE id = %s",
                   (f"{task_id}_{user_id}_{date_str}",))
    prog_row = cursor.fetchone()
    submitted = prog_row["submitted"] if prog_row else 0

    # Hitung total sudah ter-reserve
    cursor.execute("""
    SELECT COUNT(*) as count FROM sheet_urls
    WHERE task_id = %s AND date = %s AND status IN ('PENDING','PROCESSING') AND verified_by = %s
    """, (task_id, date_str, user_id_str))
    total_reserved = cursor.fetchone()["count"]

    already_counted = submitted + total_reserved
    gap = max(0, quota_staff - already_counted)

    if gap > 0:
        # Assign URL dari pool untuk menutup selisih quota
        cursor.execute("""
        SELECT id FROM sheet_urls
        WHERE task_id = %s AND date = %s AND status = 'PENDING' AND (verified_by IS NULL OR verified_by = '')
        ORDER BY created_at ASC, id ASC
        LIMIT %s
        FOR UPDATE SKIP LOCKED
        """, (task_id, date_str, gap))
        extras = cursor.fetchall()
        for r in extras:
            cursor.execute("UPDATE sheet_urls SET verified_by = %s WHERE id = %s",
                           (user_id_str, r["id"]))
        if extras:
            conn.commit()
        total_reserved += len(extras)

    cursor.close()
    conn.close()
    return total_reserved


def postgres_get_or_claim_next_url(task_id: str, date_str: str, user_id: int) -> tuple[dict | None, list[dict]]:
    from bot.config import TZ
    from datetime import datetime, timedelta
    now = datetime.now(TZ)
    user_id_str = str(user_id)

    conn = get_connection()
    cursor = conn.cursor()

    # 1. Cek PROCESSING
    cursor.execute("""
    SELECT * FROM sheet_urls 
    WHERE task_id = %s AND date = %s AND status = 'PROCESSING' AND verified_by = %s
    LIMIT 1
    """, (task_id, date_str, user_id_str))
    row = cursor.fetchone()
    if row:
        cursor.close()
        conn.close()
        return dict_clean(row), []

    # 2. Cek apakah user punya PENDING yang sudah di-assign ke dia
    cursor.execute("""
    SELECT * FROM sheet_urls
    WHERE task_id = %s AND date = %s AND status = 'PENDING' AND verified_by = %s
    ORDER BY created_at ASC, id ASC
    LIMIT 1
    FOR UPDATE
    """, (task_id, date_str, user_id_str))
    row_to_claim = cursor.fetchone()

    if row_to_claim:
        # Update status menjadi PROCESSING
        cursor.execute("""
        UPDATE sheet_urls 
        SET status = 'PROCESSING', assigned_at = %s
        WHERE id = %s
        """, (now.isoformat(), row_to_claim["id"]))
        conn.commit()

        row_to_claim["status"] = "PROCESSING"
        row_to_claim["assigned_at"] = now.isoformat()
        cursor.close()
        conn.close()
        return dict_clean(row_to_claim), []

    # Ambil quota terbaru dari task (selalu fresh dari DB)
    cursor.execute("SELECT quota_per_staff FROM tasks WHERE task_id = %s", (task_id,))
    task_row = cursor.fetchone()
    quota_staff = task_row["quota_per_staff"] if task_row else 0

    # Hitung berapa yang sudah ter-assign ke user ini (PENDING + PROCESSING)
    cursor.execute("""
    SELECT COUNT(*) as count FROM sheet_urls
    WHERE task_id = %s AND date = %s AND status IN ('PENDING', 'PROCESSING') AND verified_by = %s
    """, (task_id, date_str, user_id_str))
    total_reserved = cursor.fetchone()["count"]

    # Cek progress yang sudah di-submit
    cursor.execute("""
    SELECT submitted FROM task_progress WHERE id = %s
    """, (f"{task_id}_{user_id}_{date_str}",))
    prog_row = cursor.fetchone()
    submitted = prog_row["submitted"] if prog_row else 0

    # Hitung sisa kuota berdasarkan total keseluruhan (submitted + reserved)
    if quota_staff > 0:
        already_counted = submitted + total_reserved
        remaining_quota = max(0, quota_staff - already_counted)
        
        # Jika ada slot kosong (quota naik atau belum penuh), tambah dari pool
        if remaining_quota > 0:
            cursor.execute("""
            SELECT * FROM sheet_urls
            WHERE task_id = %s AND date = %s AND status = 'PENDING' AND (verified_by IS NULL OR verified_by = '')
            ORDER BY created_at ASC, id ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """, (task_id, date_str, remaining_quota))
            extra_rows = cursor.fetchall()
            for r in extra_rows:
                cursor.execute("""
                UPDATE sheet_urls SET verified_by = %s WHERE id = %s
                """, (user_id_str, r["id"]))
            if extra_rows:
                conn.commit()

    # 2. Cek apakah user punya PENDING yang sudah di-assign ke dia
    cursor.execute("""
    SELECT * FROM sheet_urls
    WHERE task_id = %s AND date = %s AND status = 'PENDING' AND verified_by = %s
    ORDER BY created_at ASC, id ASC
    LIMIT 1
    FOR UPDATE
    """, (task_id, date_str, user_id_str))
    row_to_claim = cursor.fetchone()

    if row_to_claim:
        cursor.execute("""
        UPDATE sheet_urls
        SET status = 'PROCESSING', assigned_at = %s
        WHERE id = %s
        """, (now.isoformat(), row_to_claim["id"]))
        conn.commit()

        row_to_claim["status"] = "PROCESSING"
        row_to_claim["assigned_at"] = now.isoformat()
        cursor.close()
        conn.close()
        return dict_clean(row_to_claim), []

    # 3. Tidak ada reserved — claim fresh block dari pool (hanya jika quota belum habis)
    if quota_staff > 0:
        remaining = max(0, quota_staff - submitted - total_reserved)
        if remaining <= 0:
            cursor.close()
            conn.close()
            return None, []
        block_size = remaining
    else:
        block_size = 20

    cursor.execute("""
    SELECT * FROM sheet_urls
    WHERE task_id = %s AND date = %s AND status = 'PENDING' AND (verified_by IS NULL OR verified_by = '')
    ORDER BY created_at ASC, id ASC
    LIMIT %s
    FOR UPDATE SKIP LOCKED
    """, (task_id, date_str, block_size))
    rows = cursor.fetchall()

    if rows:
        # Baris pertama langsung kita klaim sebagai PROCESSING
        first_row = rows[0]
        cursor.execute("""
        UPDATE sheet_urls
        SET status = 'PROCESSING', verified_by = %s, assigned_at = %s
        WHERE id = %s
        """, (user_id_str, now.isoformat(), first_row["id"]))

        # Sisa baris kita tandai verified_by = user_id_str agar ter-reserve untuk user ini
        for r in rows[1:]:
            cursor.execute("""
            UPDATE sheet_urls
            SET verified_by = %s
            WHERE id = %s
            """, (user_id_str, r["id"]))

        conn.commit()

        first_row["status"] = "PROCESSING"
        first_row["verified_by"] = user_id_str
        first_row["assigned_at"] = now.isoformat()
        cursor.close()
        conn.close()
        return dict_clean(first_row), [dict_clean(r) for r in rows]

    # 4. Cari PROCESSING ditinggal > 5 menit jika tidak ada pending sama sekali
    five_min_ago = (now - timedelta(minutes=5)).isoformat()
    cursor.execute("""
    SELECT * FROM sheet_urls 
    WHERE task_id = %s AND date = %s AND status = 'PROCESSING' AND assigned_at < %s
    ORDER BY created_at ASC, id ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
    """, (task_id, date_str, five_min_ago))
    row_to_claim = cursor.fetchone()

    if row_to_claim:
        cursor.execute("""
        UPDATE sheet_urls 
        SET status = 'PROCESSING', verified_by = %s, assigned_at = %s
        WHERE id = %s
        """, (user_id_str, now.isoformat(), row_to_claim["id"]))
        conn.commit()

        row_to_claim["status"] = "PROCESSING"
        row_to_claim["verified_by"] = user_id_str
        row_to_claim["assigned_at"] = now.isoformat()
        cursor.close()
        conn.close()
        return dict_clean(row_to_claim), []

    cursor.close()
    conn.close()
    return None, []


def postgres_list_sheet_urls(task_id: str | None = None, date: str | None = None,
                           status: str | None = None, limit: int = 50,
                           offset: int = 0, verified_by: str | None = None) -> tuple[list[dict], int]:
    conn = get_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []
    if task_id:
        where_clauses.append("task_id = %s")
        params.append(task_id)
    if date:
        where_clauses.append("date = %s")
        params.append(date)
    if status:
        where_clauses.append("status = %s")
        params.append(status)
    if verified_by:
        where_clauses.append("verified_by = %s")
        params.append(str(verified_by))

    where_str = ""
    if where_clauses:
        where_str = "WHERE " + " AND ".join(where_clauses)

    # Count total
    cursor.execute(f"SELECT COUNT(*) as count FROM sheet_urls {where_str}", tuple(params))
    total = cursor.fetchone()["count"]

    # Select limited/offsetted rows
    select_query = f"SELECT * FROM sheet_urls {where_str} ORDER BY created_at ASC, id ASC LIMIT %s OFFSET %s"
    select_params = list(params)
    select_params.extend([limit, offset])
    cursor.execute(select_query, tuple(select_params))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict_clean(r) for r in rows], total


def postgres_get_progress(task_id: str, user_id: int, date: str) -> dict | None:
    doc_id = f"{task_id}_{user_id}_{date}"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM task_progress WHERE id = %s", (doc_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict_clean(row)


def postgres_upsert_progress(task_id: str, user_id: int, date: str,
                           submitted_delta: int = 0, ok_delta: int = 0,
                           fail_delta: int = 0):
    doc_id = f"{task_id}_{user_id}_{date}"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM task_progress WHERE id = %s", (doc_id,))
    row = cursor.fetchone()
    if row:
        cursor.execute("""
        UPDATE task_progress 
        SET submitted = submitted + %s, verified_ok = verified_ok + %s, verified_fail = verified_fail + %s
        WHERE id = %s
        """, (submitted_delta, ok_delta, fail_delta, doc_id))
    else:
        cursor.execute("""
        INSERT INTO task_progress (id, task_id, user_id, date, submitted, verified_ok, verified_fail)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (doc_id, task_id, user_id, date, submitted_delta, ok_delta, fail_delta))
    conn.commit()
    cursor.close()
    conn.close()


def postgres_list_progress_by_date(date: str) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM task_progress WHERE date = %s", (date,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict_clean(r) for r in rows]


def postgres_list_progress_by_user(user_id: int, limit: int = 21) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM task_progress WHERE user_id = %s
    ORDER BY date DESC LIMIT %s
    """, (user_id, limit))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict_clean(r) for r in rows]


def postgres_add_audit_log(actor_id: int, action: str, target_type: str,
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
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (doc_id, actor_id, action, target_type, target_id, detail_str, timestamp))
    conn.commit()
    cursor.close()
    conn.close()


def postgres_get_user_active_tasks_today(user_id: int, date_str: str) -> list[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT DISTINCT task_id FROM sheet_urls
    WHERE verified_by = %s AND date = %s AND status IN ('PROCESSING', 'PENDING')
    """, (str(user_id), date_str))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [r["task_id"] for r in rows]


def postgres_reset_today(date_str: str) -> tuple[int, int]:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM sheet_urls WHERE date = %s", (date_str,))
    urls_deleted = cursor.rowcount
    
    cursor.execute("DELETE FROM task_progress WHERE date = %s", (date_str,))
    progress_deleted = cursor.rowcount
    
    conn.commit()
    cursor.close()
    conn.close()
    return urls_deleted, progress_deleted


def postgres_retry_failed_urls(date_str: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT id, task_id, verified_by FROM sheet_urls
    WHERE date = %s AND status IN ('TIMEOUT', 'HTTP_ERR', 'FORMAT_ERR', 'ERROR')
    """, (date_str,))
    rows = cursor.fetchall()
    
    if not rows:
        cursor.close()
        conn.close()
        return 0
        
    count = 0
    for r in rows:
        doc_id = r["id"]
        task_id = r["task_id"]
        v_by = r["verified_by"]
        
        cursor.execute("""
        UPDATE sheet_urls
        SET status = 'PENDING',
            verified_by = NULL,
            verified_at = NULL,
            error_msg = NULL,
            http_code = NULL,
            api_key_status = NULL
        WHERE id = %s
        """, (doc_id,))
        
        if v_by and str(v_by).isdigit():
            try:
                user_id = int(v_by)
                cursor.execute("""
                UPDATE task_progress
                SET submitted = GREATEST(0, submitted - 1),
                    verified_fail = GREATEST(0, verified_fail - 1)
                WHERE task_id = %s AND user_id = %s AND date = %s
                """, (task_id, user_id, date_str))
            except Exception:
                pass
        count += 1
        
    conn.commit()
    cursor.close()
    conn.close()
    return count


def postgres_get_all_failed_urls(date_str: str | None = None) -> list[dict]:
    """Ambil URL gagal. Jika date_str diberikan, filter hanya untuk tanggal tsb (UTC)."""
    conn = get_connection()
    cursor = conn.cursor()
    if date_str:
        cursor.execute("""
        SELECT * FROM sheet_urls
        WHERE status IN ('TIMEOUT', 'HTTP_ERR', 'ERROR')
          AND date = %s
        ORDER BY created_at ASC
        """, (date_str,))
    else:
        cursor.execute("""
        SELECT * FROM sheet_urls
        WHERE status IN ('TIMEOUT', 'HTTP_ERR', 'ERROR')
        ORDER BY created_at ASC
        """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict_clean(r) for r in rows]


def postgres_sync_task_assignments(task_id: str, date_str: str) -> list[dict]:
    task = postgres_get_task(task_id)
    if not task:
        return []
    quota_staff = task.get("quota_per_staff", 0)
    if quota_staff <= 0:
        return []

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT verified_by FROM sheet_urls
        WHERE task_id = %s AND date = %s AND verified_by IS NOT NULL AND verified_by != ''
    """, (task_id, date_str))
    user_rows = cursor.fetchall()

    newly_assigned_urls = []

    for u_row in user_rows:
        user_id_str = u_row["verified_by"]
        if not user_id_str:
            continue

        cursor.execute("""
            SELECT COUNT(*) as count FROM sheet_urls
            WHERE task_id = %s AND date = %s AND verified_by = %s
        """, (task_id, date_str, user_id_str))
        total_assigned = cursor.fetchone()["count"]

        if total_assigned < quota_staff:
            needed = quota_staff - total_assigned
            
            cursor.execute("""
                SELECT * FROM sheet_urls
                WHERE task_id = %s AND date = %s AND status = 'PENDING' AND (verified_by IS NULL OR verified_by = '')
                ORDER BY created_at ASC, id ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            """, (task_id, date_str, needed))
            pending_rows = cursor.fetchall()
            
            for r in pending_rows:
                cursor.execute("""
                    UPDATE sheet_urls
                    SET verified_by = %s
                    WHERE id = %s
                """, (user_id_str, r["id"]))
                newly_assigned_urls.append(r)

    conn.commit()
    cursor.close()
    conn.close()
    return [dict_clean(r) for r in newly_assigned_urls]
