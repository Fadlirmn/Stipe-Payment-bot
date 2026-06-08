"""
firebase_db.py — Firebase Firestore wrapper
Menggantikan SQLAlchemy. Semua data disimpan di Firestore.

Koleksi Firestore:
  users/          {user_id (str)}
  tasks/          {task_id}
  sheet_urls/     {auto-id}
  task_progress/  {task_id}_{user_id}_{date}
  audit_logs/     {auto-id}
"""
from __future__ import annotations

import firebase_admin
from firebase_admin import credentials, firestore
from loguru import logger
import time

import warnings
# Abaikan warning deprecation dari Firestore SDK agar log tidak penuh spam
warnings.filterwarnings("ignore", category=UserWarning, message="Detected filter using positional arguments.*")

from bot.config import FIREBASE_CREDENTIALS_JSON, FIREBASE_PROJECT_ID

# ── User Cache ────────────────────────────────────────────
_user_cache: dict[int, tuple[dict | None, float]] = {}
USER_CACHE_TTL = 120.0  # 2 minutes cache duration

# ── Init Firebase (singleton) ─────────────────────────────
_app = None

def get_db() -> firestore.AsyncClient:
    global _app
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_JSON)
        _app = firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
        logger.info(f"[Firebase] Initialized project={FIREBASE_PROJECT_ID}")
    return firestore.AsyncClient(project=FIREBASE_PROJECT_ID,
                                  credentials=firebase_admin.get_app().credential.get_credential())


# ── Shared async client instance ──────────────────────────
_db: firestore.AsyncClient | None = None

def db() -> firestore.AsyncClient:
    global _db
    if _db is None:
        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_CREDENTIALS_JSON)
            firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
            logger.info(f"[Firebase] Initialized project={FIREBASE_PROJECT_ID}")
        # Ambil credentials dari firebase_admin app yang sudah diinit
        google_cred = firebase_admin.get_app().credential.get_credential()
        _db = firestore.AsyncClient(
            project=FIREBASE_PROJECT_ID,
            credentials=google_cred,
        )
        logger.info(f"[Firebase] Initialized project={FIREBASE_PROJECT_ID}")
    return _db


# ── Collections ───────────────────────────────────────────
def users_col():       return db().collection("users")
def tasks_col():       return db().collection("tasks")
def sheet_urls_col():  return db().collection("sheet_urls")
def progress_col():    return db().collection("task_progress")
def audit_col():       return db().collection("audit_logs")


# ══════════════════════════════════════════════════════════
# USER HELPERS
# ══════════════════════════════════════════════════════════
async def get_user(user_id: int) -> dict | None:
    now = time.time()
    if user_id in _user_cache:
        data, expiry = _user_cache[user_id]
        if now < expiry:
            return data

    doc = await users_col().document(str(user_id)).get()
    user_data = doc.to_dict() if doc.exists else None
    _user_cache[user_id] = (user_data, now + USER_CACHE_TTL)
    return user_data


async def create_user(user_id: int, username: str, full_name: str, role: str = "pending") -> dict:
    from datetime import datetime
    from bot.config import TZ
    data = {
        "user_id":    user_id,
        "username":   username,
        "full_name":  full_name,
        "role":       role,
        "is_active":  True,
        "joined_at":  datetime.now(TZ).isoformat(),
        "approved_by": None,
    }
    await users_col().document(str(user_id)).set(data)
    _user_cache[user_id] = (data, time.time() + USER_CACHE_TTL)
    return data


async def update_user(user_id: int, **kwargs):
    await users_col().document(str(user_id)).update(kwargs)
    if user_id in _user_cache:
        del _user_cache[user_id]


async def list_users(role: str | None = None) -> list[dict]:
    q = users_col()
    if role:
        q = q.where("role", "==", role)
    docs = await q.get()
    return [d.to_dict() for d in docs]


# ── Task Cache ────────────────────────────────────────────
_task_cache: dict[str, tuple[dict | None, float]] = {}
TASK_CACHE_TTL = 300.0  # 5 minutes cache duration

# ══════════════════════════════════════════════════════════
# TASK HELPERS
# ══════════════════════════════════════════════════════════
async def get_task(task_id: str) -> dict | None:
    now = time.time()
    if task_id in _task_cache:
        data, expiry = _task_cache[task_id]
        if now < expiry:
            return data

    doc = await tasks_col().document(task_id).get()
    task_data = doc.to_dict() if doc.exists else None
    _task_cache[task_id] = (task_data, now + TASK_CACHE_TTL)
    return task_data


async def create_task(task_data: dict) -> dict:
    from datetime import datetime
    from bot.config import TZ
    task_data["created_at"] = datetime.now(TZ).isoformat()
    await tasks_col().document(task_data["task_id"]).set(task_data)
    _task_cache[task_data["task_id"]] = (task_data, time.time() + TASK_CACHE_TTL)
    return task_data


async def update_task(task_id: str, **kwargs):
    await tasks_col().document(task_id).update(kwargs)
    if task_id in _task_cache:
        del _task_cache[task_id]


async def list_tasks(status: str | None = "active") -> list[dict]:
    q = tasks_col()
    if status:
        q = q.where("status", "==", status)
    docs = await q.get()
    return [d.to_dict() for d in docs]


# ══════════════════════════════════════════════════════════
# SHEET URL HELPERS
# ══════════════════════════════════════════════════════════
async def add_sheet_url(task_id: str, date: str, account: str,
                         payment_url: str, notes: str, check_exists: bool = True) -> str:
    """Tambah URL ke Firestore. Return doc_id."""
    from datetime import datetime
    import hashlib
    from bot.config import TZ

    # Buat ID dokumen unik berbasis hash md5 dari task_id dan payment_url
    doc_id = hashlib.md5(f"{task_id}_{payment_url}".encode("utf-8")).hexdigest()
    ref = sheet_urls_col().document(doc_id)

    if check_exists:
        doc_snap = await ref.get()
        if doc_snap.exists:
            # Jika sudah ada, jangan timpa datanya untuk mencegah hilangnya status verifikasi jika disinkronkan ulang
            return doc_id

    data = {
        "task_id":     task_id,
        "date":        date,
        "account":     account,
        "payment_url": payment_url,
        "notes":       notes,
        "status":      "PENDING",
        "http_code":   None,
        "error_msg":   None,
        "verified_by": None,
        "verified_at": None,
        "created_at":  datetime.now(TZ).isoformat(),
    }
    await ref.set(data)
    return doc_id


async def get_sheet_url(doc_id: str) -> dict | None:
    doc = await sheet_urls_col().document(doc_id).get()
    if not doc.exists:
        return None
    d = doc.to_dict()
    d["id"] = doc.id
    return d


async def update_sheet_url(doc_id: str, **kwargs):
    await sheet_urls_col().document(doc_id).update(kwargs)


async def count_sheet_urls(task_id: str, date: str,
                             status: str | None = None) -> int:
    q = (sheet_urls_col()
         .where("task_id", "==", task_id)
         .where("date", "==", date))
    if status:
        q = q.where("status", "==", status)
    
    count_query = q.count()
    res = await count_query.get()
    return int(res[0].value) if res else 0


async def get_next_pending_url(task_id: str, date: str) -> dict | None:
    docs = await (
        sheet_urls_col()
        .where("task_id", "==", task_id)
        .where("date", "==", date)
        .where("status", "==", "PENDING")
        .limit(1)
        .get()
    )
    if not docs:
        return None
    d = docs[0].to_dict()
    d["id"] = docs[0].id
    return d


async def get_or_claim_next_url(task_id: str, date_str: str, user_id: int) -> dict | None:
    """
    Mengambil URL yang sedang diproses oleh staff ini, atau mengklaim URL PENDING berikutnya.
    Menggunakan optimistic update (bukan Firestore transaction) karena SDK async_transactional
    bermasalah dengan versi google-cloud-firestore saat ini.
    """
    from datetime import datetime, timedelta
    from bot.config import TZ
    import asyncio

    user_id_str = str(user_id)

    # 1. Cek apakah staff ini sudah memiliki URL berstatus PROCESSING
    user_processing_docs = await (
        sheet_urls_col()
        .where("task_id", "==", task_id)
        .where("date", "==", date_str)
        .where("status", "==", "PROCESSING")
        .where("verified_by", "==", user_id_str)
        .limit(1)
        .get()
    )
    if user_processing_docs:
        d = user_processing_docs[0].to_dict()
        d["id"] = user_processing_docs[0].id
        return d

    # 2. Cari & klaim URL dengan optimistic update (retry max 3x)
    for attempt in range(3):
        now = datetime.now(TZ)

        # Cari PENDING
        pending_docs = await (
            sheet_urls_col()
            .where("task_id", "==", task_id)
            .where("date", "==", date_str)
            .where("status", "==", "PENDING")
            .limit(1)
            .get()
        )

        doc_to_claim = None
        if pending_docs:
            doc_to_claim = pending_docs[0]
        else:
            # Cari PROCESSING yang sudah ditinggal > 5 menit
            five_min_ago = (now - timedelta(minutes=5)).isoformat()
            abandoned_docs = await (
                sheet_urls_col()
                .where("task_id", "==", task_id)
                .where("date", "==", date_str)
                .where("status", "==", "PROCESSING")
                .where("assigned_at", "<", five_min_ago)
                .limit(1)
                .get()
            )
            if abandoned_docs:
                doc_to_claim = abandoned_docs[0]

        if not doc_to_claim:
            return None  # Semua URL sudah habis

        data = doc_to_claim.to_dict()
        curr_status = data.get("status")
        curr_assigned_at = data.get("assigned_at")

        is_pending   = (curr_status == "PENDING")
        is_abandoned = (
            curr_status == "PROCESSING" and
            curr_assigned_at and
            curr_assigned_at < (now - timedelta(minutes=5)).isoformat()
        )

        if not (is_pending or is_abandoned):
            # URL sudah diambil orang lain — coba lagi
            if attempt < 2:
                await asyncio.sleep(0.3)
            continue

        # Update langsung (optimistic — tanpa transaction)
        try:
            doc_ref = sheet_urls_col().document(doc_to_claim.id)
            await doc_ref.update({
                "status":      "PROCESSING",
                "verified_by": user_id_str,
                "assigned_at": now.isoformat(),
            })
            data["id"]          = doc_to_claim.id
            data["status"]      = "PROCESSING"
            data["verified_by"] = user_id_str
            return data
        except Exception as e:
            logger.warning(f"[Claim] attempt {attempt+1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(0.3)

    return None



async def list_sheet_urls(task_id: str | None = None, date: str | None = None,
                           status: str | None = None, limit: int = 50,
                           offset: int = 0) -> tuple[list[dict], int]:
    q = sheet_urls_col()
    if task_id: q = q.where("task_id", "==", task_id)
    if date:    q = q.where("date", "==", date)
    if status:  q = q.where("status", "==", status)

    # 1. Hitung total secara efisien menggunakan count() query server-side
    count_query = q.count()
    count_snap = await count_query.get()
    total = int(count_snap[0].value) if count_snap else 0

    # 2. Ambil hanya sesuai limit dan offset di query database untuk menghemat quota read
    # Kita tidak menggunakan order_by di query agar tidak membutuhkan composite index tambahan di Firestore
    query_with_limit = q.limit(limit).offset(offset)
    docs = await query_with_limit.get()
    
    docs_data = []
    for d in docs:
        item = d.to_dict()
        item["id"] = d.id
        docs_data.append(item)
        
    return docs_data, total


# ══════════════════════════════════════════════════════════
# TASK PROGRESS HELPERS
# ══════════════════════════════════════════════════════════
def _prog_id(task_id: str, user_id: int, date: str) -> str:
    return f"{task_id}_{user_id}_{date}"


async def get_progress(task_id: str, user_id: int, date: str) -> dict | None:
    doc = await progress_col().document(_prog_id(task_id, user_id, date)).get()
    return doc.to_dict() if doc.exists else None


async def upsert_progress(task_id: str, user_id: int, date: str,
                           submitted_delta: int = 0, ok_delta: int = 0,
                           fail_delta: int = 0):
    doc_id = _prog_id(task_id, user_id, date)
    ref    = progress_col().document(doc_id)
    existing = await ref.get()
    if existing.exists:
        data = existing.to_dict()
        await ref.update({
            "submitted":     data["submitted"]     + submitted_delta,
            "verified_ok":   data["verified_ok"]   + ok_delta,
            "verified_fail": data["verified_fail"]  + fail_delta,
        })
    else:
        await ref.set({
            "task_id":       task_id,
            "user_id":       user_id,
            "date":          date,
            "submitted":     submitted_delta,
            "verified_ok":   ok_delta,
            "verified_fail": fail_delta,
        })


async def list_progress_by_date(date: str) -> list[dict]:
    docs = await progress_col().where("date", "==", date).get()
    return [d.to_dict() for d in docs]


async def list_progress_by_user(user_id: int, limit: int = 21) -> list[dict]:
    # Ambil tanpa order_by di query agar tidak memerlukan composite index di Firestore
    docs = await (progress_col()
                  .where("user_id", "==", user_id)
                  .get())
    res = [d.to_dict() for d in docs]
    # Urutkan di memori (date DESC)
    res.sort(key=lambda x: x.get("date", ""), reverse=True)
    return res[:limit]



# ══════════════════════════════════════════════════════════
# AUDIT LOG
# ══════════════════════════════════════════════════════════
async def add_audit_log(actor_id: int, action: str, target_type: str,
                         target_id: str, detail: dict | None = None):
    from datetime import datetime
    from bot.config import TZ
    await audit_col().add({
        "actor_id":    actor_id,
        "action":      action,
        "target_type": target_type,
        "target_id":   target_id,
        "detail":      detail or {},
        "timestamp":   datetime.now(TZ).isoformat(),
    })


async def init_db():
    """Panggil saat startup untuk memvalidasi koneksi Firebase."""
    try:
        # Coba baca satu dokumen untuk test koneksi
        await tasks_col().limit(1).get()
        logger.info("[Firebase] Firestore connection OK")
    except Exception as e:
        logger.error(f"[Firebase] Connection failed: {e}")
        raise
