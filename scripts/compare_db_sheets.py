#!/usr/bin/env python3
"""
scripts/compare_db_sheets.py
Bandingkan data antara PostgreSQL lokal dengan Google Sheets (via Apps Script).
Menemukan perbedaan status atau link yang belum tersinkronisasi.
"""
import os
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor

# Load env
load_dotenv()

PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB = os.getenv("POSTGRES_DB", "stripe_verif")
PG_USER = os.getenv("POSTGRES_USER", "postgres")
PG_PWD = os.getenv("POSTGRES_PASSWORD", "postgres")
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "")

async def fetch_sheets_pending():
    """Mengambil baris PENDING (belum ada status) dari Google Sheets."""
    if not APPS_SCRIPT_URL:
        print("❌ APPS_SCRIPT_URL tidak ditemukan di .env")
        return []
    today = datetime.now(timezone.utc).date().isoformat()
    params = {"date": today, "tab": "Sheet1"}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(APPS_SCRIPT_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()
            return payload.get("data", [])
    except Exception as e:
        print(f"❌ Gagal memanggil Google Sheets: {e}")
        return []

def fetch_db_urls():
    """Mengambil semua URL hari ini dari PostgreSQL."""
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, database=PG_DB,
            user=PG_USER, password=PG_PWD,
            cursor_factory=RealDictCursor
        )
        cursor = conn.cursor()
        cursor.execute("""
            SELECT payment_url, status, verified_by, verified_at, api_key_status 
            FROM sheet_urls 
            WHERE date = %s
        """, (today,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"❌ Gagal koneksi ke PostgreSQL: {e}")
        return []

async def main():
    print("🔍 MEMULAI PEMBANDINGAN DATA (HARI INI - UTC)...")
    print("=" * 60)
    
    db_urls = fetch_db_urls()
    sheets_pending = await fetch_sheets_pending()
    
    db_map = {u["payment_url"].strip(): u for u in db_urls}
    sheet_urls_set = {s["payment_url"].strip() for s in sheets_pending}
    
    print(f"📊 PostgreSQL: {len(db_urls)} record ditemukan.")
    print(f"📊 Google Sheets (Pending): {len(sheets_pending)} record ditemukan.")
    print("-" * 60)
    
    # 1. Cari yang ada di Sheets tapi BELUM ada di DB (Belum Sync)
    not_in_db = []
    for row in sheets_pending:
        url = row["payment_url"].strip()
        if url not in db_map:
            not_in_db.append(row)
            
    if not_in_db:
        print(f"⚠️ {len(not_in_db)} URL di Google Sheets BELUM masuk ke database (perlu /sync_sheets):")
        for idx, row in enumerate(not_in_db, 1):
            print(f"  {idx}. {row.get('account')} -> {row.get('payment_url')}")
    else:
        print("✅ Semua URL pending dari Google Sheets sudah tersimpan di database.")
        
    print("-" * 60)
    
    # 2. Cari URL di database yang berstatus VERIFIED (OK/FAIL) tapi mungkin gagal update di Sheets
    # (Karena doGet hanya mengembalikan yang kosong, kita tidak bisa langsung cek status di Sheets
    #  tetapi jika di DB sudah berstatus selain PENDING/PROCESSING, maka di Sheets idealnya sudah terisi).
    verified_db = [u for u in db_urls if u["status"] not in ("PENDING", "PROCESSING")]
    
    # URL di DB yang berstatus verified tetapi masih muncul di list pending Sheets
    failed_writeback = []
    for u in verified_db:
        url = u["payment_url"].strip()
        if url in sheet_urls_set:
            failed_writeback.append(u)
            
    if failed_writeback:
        print(f"❌ Terdeteksi {len(failed_writeback)} URL sudah diverifikasi di DB tetapi status di Sheets masih kosong (Gagal Update):")
        for idx, u in enumerate(failed_writeback, 1):
            print(f"  {idx}. Status DB: {u['status']} -> {u['payment_url']}")
        print("\n💡 Tips: Anda dapat menjalankan tombol/fitur re-verify untuk memperbarui status di Google Sheets secara paksa.")
    else:
        print("✅ Tidak ada indikasi kegagalan penulisan status dari DB ke Google Sheets.")
        
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
