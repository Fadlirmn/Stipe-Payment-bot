"""
api_main.py — FastAPI Web API backend for Stripe Verification Bot Dashboard.
Supports both Local SQLite and PostgreSQL dynamically based on env configuration.
"""
from __future__ import annotations

import os
import re
import sqlite3
import json
import hashlib
from datetime import datetime, timedelta
from typing import List, Any, Optional
from loguru import logger
import jwt

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

DB_PATH = "data/backup.db"
JWT_SECRET = os.getenv("JWT_SECRET", "stripe_verif_default_jwt_secret_998811")
ALGORITHM = "HS256"

# Check if PostgreSQL is enabled
USE_POSTGRES = bool(os.getenv("POSTGRES_HOST"))

app = FastAPI(title="Stripe Verif Bot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# Initialize appropriate database
if USE_POSTGRES:
    from bot.postgres_db import postgres_init_db
    postgres_init_db()
else:
    from bot.sqlite_db import sqlite_init_db
    sqlite_init_db()

# --- Helpers ---
def is_safe_identifier(name: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_]+$", name))

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return dict_clean(d)

def dict_clean(d):
    if not d:
        return d
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

def get_db_connection():
    if USE_POSTGRES:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "stripe_verif"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            cursor_factory=RealDictCursor
        )
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = dict_factory
        return conn

# --- Password Hashing ---
def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        salt.encode('utf-8'), 
        100000
    ).hex()
    return f"{salt}:{pwd_hash}"

def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash or ":" not in stored_hash:
        return False
    salt, pwd_hash = stored_hash.split(":")
    expected_hash = hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        salt.encode('utf-8'), 
        100000
    ).hex()
    return expected_hash == pwd_hash

# --- JWT Helpers ---
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=7))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token tidak valid atau kedaluwarsa")

# --- Auth Schemas & Endpoints ---
class SigninRequest(BaseModel):
    email: str
    password: str

class SignupRequest(BaseModel):
    email: str
    password: str

class TelegramLoginRequest(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = ""
    username: Optional[str] = ""
    photo_url: Optional[str] = ""
    auth_date: int
    hash: str

@app.post("/api/auth/signup")
async def api_signup(req: SignupRequest):
    email_lower = req.email.lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    placeholder = "%s" if USE_POSTGRES else "?"
    cursor.execute(f"SELECT * FROM users WHERE LOWER(email) = {placeholder}", (email_lower,))
    user = cursor.fetchone()

    if not user:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Email belum dihubungkan ke akun Telegram bot. Hubungkan dulu di bot via /setemail.")

    user_dict = dict_clean(user)
    pwd_hash = hash_password(req.password)
    cursor.execute(f"UPDATE users SET password_hash = {placeholder} WHERE user_id = {placeholder}", (pwd_hash, user_dict["user_id"]))
    conn.commit()
    cursor.close()
    conn.close()
    return {"ok": True}

@app.post("/api/auth/signin")
async def api_signin(req: SigninRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    placeholder = "%s" if USE_POSTGRES else "?"
    cursor.execute(f"SELECT * FROM users WHERE LOWER(email) = {placeholder}", (req.email.lower(),))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="Email tidak terdaftar.")

    user_dict = dict_clean(user)
    if not user_dict.get("is_active"):
        raise HTTPException(status_code=401, detail="Akun Anda dinonaktifkan.")

    stored_hash = user_dict.get("password_hash")
    if not stored_hash:
        raise HTTPException(status_code=400, detail="Akun belum didaftarkan untuk dashboard. Silakan lakukan Sign Up terlebih dahulu.")

    if not verify_password(req.password, stored_hash):
        raise HTTPException(status_code=401, detail="Password salah.")

    token_data = {
        "user_id": user_dict["user_id"],
        "username": user_dict["username"],
        "full_name": user_dict["full_name"],
        "role": user_dict["role"],
        "email": req.email.lower()
    }
    token = create_access_token(token_data)
    return {"ok": True, "token": token, "user": token_data}

@app.post("/api/auth/telegram")
async def api_auth_telegram(req: TelegramLoginRequest):
    import hmac
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN tidak terkonfigurasi pada server.")

    data_dict = req.dict(exclude={"hash"})
    filtered_data = {k: str(v) for k, v in data_dict.items() if v is not None}
    check_string = "\n".join(f"{k}={filtered_data[k]}" for k in sorted(filtered_data.keys()))

    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    expected_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()

    if expected_hash != req.hash:
        raise HTTPException(status_code=401, detail="Data autentikasi Telegram tidak valid.")

    import time
    if time.time() - req.auth_date > 86400:
        raise HTTPException(status_code=401, detail="Sesi Telegram kedaluwarsa.")

    conn = get_db_connection()
    cursor = conn.cursor()
    
    placeholder = "%s" if USE_POSTGRES else "?"
    cursor.execute(f"SELECT * FROM users WHERE user_id = {placeholder}", (req.id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=400, detail="Akun Telegram Anda belum terdaftar di bot. Mulai bot dulu.")

    user_dict = dict_clean(user)
    if not user_dict.get("is_active"):
        raise HTTPException(status_code=400, detail="Akun Anda dinonaktifkan.")

    token_data = {
        "user_id": user_dict["user_id"],
        "username": user_dict["username"],
        "full_name": user_dict["full_name"],
        "role": user_dict["role"],
        "email": user_dict.get("email", "")
    }
    token = create_access_token(token_data)
    return {"ok": True, "token": token, "user": token_data}

# --- Generic Query Schemas & Endpoints ---
class QueryRequest(BaseModel):
    collectionPath: str
    conditions: List[List[Any]] = []
    orderByField: Optional[str] = None
    orderDir: Optional[str] = "desc"
    limitN: Optional[int] = None

class CountRequest(BaseModel):
    collectionPath: str
    conditions: List[List[Any]] = []

class UpdateRequest(BaseModel):
    collectionPath: str
    docId: str
    updateData: dict

VALID_TABLES = {"users", "tasks", "sheet_urls", "task_progress", "audit_logs"}

@app.post("/api/query")
async def api_query(req: QueryRequest, user: dict = Depends(get_current_user)):
    if req.collectionPath not in VALID_TABLES:
        raise HTTPException(status_code=400, detail="Invalid collection path")

    placeholder = "%s" if USE_POSTGRES else "?"
    where_clauses = []
    params = []
    for cond in req.conditions:
        if len(cond) != 3:
            continue
        field, op, val = cond
        if not is_safe_identifier(field):
            raise HTTPException(status_code=400, detail=f"Invalid field name: {field}")
        
        if op == "==":
            sql_op = "="
        elif op in ("<", ">", "<=", ">="):
            sql_op = op
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported operator: {op}")
        where_clauses.append(f"{field} {sql_op} {placeholder}")
        params.append(val)

    where_str = ""
    if where_clauses:
        where_str = "WHERE " + " AND ".join(where_clauses)

    order_str = ""
    if req.orderByField:
        if not is_safe_identifier(req.orderByField):
            raise HTTPException(status_code=400, detail="Invalid order field name")
        direction = "DESC" if req.orderDir and req.orderDir.lower() == "desc" else "ASC"
        order_str = f"ORDER BY {req.orderByField} {direction}"

    limit_str = ""
    if req.limitN is not None:
        limit_str = f"LIMIT {int(req.limitN)}"

    sql = f"SELECT * FROM {req.collectionPath} {where_str} {order_str} {limit_str}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    results = [dict_clean(r) for r in rows]
    return {"results": results}

@app.post("/api/count")
async def api_count(req: CountRequest, user: dict = Depends(get_current_user)):
    if req.collectionPath not in VALID_TABLES:
        raise HTTPException(status_code=400, detail="Invalid collection path")

    placeholder = "%s" if USE_POSTGRES else "?"
    where_clauses = []
    params = []
    for cond in req.conditions:
        if len(cond) != 3:
            continue
        field, op, val = cond
        if not is_safe_identifier(field):
            raise HTTPException(status_code=400, detail=f"Invalid field name: {field}")
        
        if op == "==":
            sql_op = "="
        elif op in ("<", ">", "<=", ">="):
            sql_op = op
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported operator: {op}")
        where_clauses.append(f"{field} {sql_op} {placeholder}")
        params.append(val)

    where_str = ""
    if where_clauses:
        where_str = "WHERE " + " AND ".join(where_clauses)

    sql = f"SELECT COUNT(*) as count FROM {req.collectionPath} {where_str}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, tuple(params))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    row_dict = dict_clean(row)
    return {"count": row_dict["count"] if row_dict else 0}

@app.post("/api/update")
async def api_update(req: UpdateRequest, user: dict = Depends(get_current_user)):
    if req.collectionPath not in VALID_TABLES:
        raise HTTPException(status_code=400, detail="Invalid collection path")

    if not req.updateData:
        return {"ok": True}

    placeholder = "%s" if USE_POSTGRES else "?"
    keys = list(req.updateData.keys())
    values = list(req.updateData.values())

    for k in keys:
        if not is_safe_identifier(k):
            raise HTTPException(status_code=400, detail=f"Invalid update key: {k}")

    pk_column = "user_id" if req.collectionPath == "users" else "task_id" if req.collectionPath == "tasks" else "id"

    # Convert values to compatible types
    for i, val in enumerate(values):
        if isinstance(val, bool):
            values[i] = 1 if val else 0
        elif isinstance(val, (dict, list)):
            values[i] = json.dumps(val)

    set_clause = ", ".join([f"{k} = {placeholder}" for k in keys])
    
    actual_doc_id = int(req.docId) if req.collectionPath == "users" and req.docId.isdigit() else req.docId
    values.append(actual_doc_id)

    sql = f"UPDATE {req.collectionPath} SET {set_clause} WHERE {pk_column} = {placeholder}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, tuple(values))
    conn.commit()
    cursor.close()
    conn.close()
    return {"ok": True}
