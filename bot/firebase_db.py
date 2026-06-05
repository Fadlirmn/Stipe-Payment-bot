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

from bot.config import FIREBASE_CREDENTIALS_JSON, FIREBASE_PROJECT_ID

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
    doc = await users_col().document(str(user_id)).get()
    return doc.to_dict() if doc.exists else None


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
    return data


async def update_user(user_id: int, **kwargs):
    await users_col().document(str(user_id)).update(kwargs)


async def list_users(role: str | None = None) -> list[dict]:
    q = users_col()
    if role:
        q = q.where("role", "==", role)
    docs = await q.get()
    return [d.to_dict() for d in docs]


# ══════════════════════════════════════════════════════════
# TASK HELPERS
# ══════════════════════════════════════════════════════════
async def get_task(task_id: str) -> dict | None:
    doc = await tasks_col().document(task_id).get()
    return doc.to_dict() if doc.exists else None


async def create_task(task_data: dict) -> dict:
    from datetime import datetime
    from bot.config import TZ
    task_data["created_at"] = datetime.now(TZ).isoformat()
    await tasks_col().document(task_data["task_id"]).set(task_data)
    return task_data


async def update_task(task_id: str, **kwargs):
    await tasks_col().document(task_id).update(kwargs)


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
                         payment_url: str, notes: str) -> str:
    """Tambah URL ke Firestore. Return doc_id."""
    from datetime import datetime
    import hashlib
    from bot.config import TZ

    # Buat ID dokumen unik berbasis hash md5 dari task_id dan payment_url
    doc_id = hashlib.md5(f"{task_id}_{payment_url}".encode("utf-8")).hexdigest()
    ref = sheet_urls_col().document(doc_id)

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
    docs = await q.get()
    return len(docs)


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
    Mengambil URL yang sedang diproses oleh staff ini, atau mengklaim URL PENDING berikutnya
    menggunakan transaksi Firestore agar tidak terjadi klaim ganda oleh staff lain.
    Juga mendeteksi dan mengklaim ulang URL berstatus PROCESSING yang sudah kedaluwarsa (> 5 menit).
    """
    from google.cloud.firestore import async_transactional
    from datetime import datetime, timedelta
    from bot.config import TZ

    db_client = get_db()
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

    # 2. Cari kandidat URL PENDING atau PROCESSING kedaluwarsa, lalu klaim dengan transaksi
    for _ in range(3): # Coba 3 kali jika ada konflik transaksi
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
        
        doc_id = None
        if pending_docs:
            doc_id = pending_docs[0].id
        else:
            # Jika tidak ada yang PENDING, cari PROCESSING yang sudah ditinggal (> 5 menit)
            five_minutes_ago = (now - timedelta(minutes=5)).isoformat()
            abandoned_docs = await (
                sheet_urls_col()
                .where("task_id", "==", task_id)
                .where("date", "==", date_str)
                .where("status", "==", "PROCESSING")
                .where("assigned_at", "<", five_minutes_ago)
                .limit(1)
                .get()
            )
            if abandoned_docs:
                doc_id = abandoned_docs[0].id
                
        if not doc_id:
            return None # Habis
            
        doc_ref = sheet_urls_col().document(doc_id)
        
        @async_transactional
        async def _claim_tx(transaction, doc_ref):
            doc_snap = await transaction.get(doc_ref)
            if not doc_snap.exists:
                return None
                
            data = doc_snap.to_dict()
            curr_status = data.get("status")
            curr_assigned_at = data.get("assigned_at")
            
            # Validasi kelayakan klaim dalam transaksi
            is_pending = (curr_status == "PENDING")
            is_abandoned = (
                curr_status == "PROCESSING" and 
                curr_assigned_at and 
                curr_assigned_at < (datetime.now(TZ) - timedelta(minutes=5)).isoformat()
            )
            
            if is_pending or is_abandoned:
                transaction.update(doc_ref, {
                    "status": "PROCESSING",
                    "verified_by": user_id_str,
                    "assigned_at": datetime.now(TZ).isoformat()
                })
                data["id"] = doc_snap.id
                data["status"] = "PROCESSING"
                data["verified_by"] = user_id_str
                return data
            return None
            
        claimed = await _claim_tx(db_client.transaction(), doc_ref)
        if claimed:
            return claimed
            
    return None


async def list_sheet_urls(task_id: str | None = None, date: str | None = None,
                           status: str | None = None, limit: int = 50,
                           offset: int = 0) -> tuple[list[dict], int]:
    q = sheet_urls_col()
    if task_id: q = q.where("task_id", "==", task_id)
    if date:    q = q.where("date", "==", date)
    if status:  q = q.where("status", "==", status)

    all_docs = await q.order_by("created_at", direction=firestore.Query.DESCENDING).get()
    total = len(all_docs)
    sliced = all_docs[offset: offset + limit]
    result = []
    for d in sliced:
        item = d.to_dict()
        item["id"] = d.id
        result.append(item)
    return result, total


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
    docs = await (progress_col()
                  .where("user_id", "==", user_id)
                  .order_by("date", direction=firestore.Query.DESCENDING)
                  .limit(limit)
                  .get())
    return [d.to_dict() for d in docs]


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
