import sys
import os
import asyncio
from datetime import datetime, timezone

# Add project root to sys.path to resolve imports correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bot.db as fdb
from bot.services.sheet_parser import update_sheet_status
from bot.postgres_db import get_connection

async def main():
    today_utc = datetime.now(timezone.utc).date().isoformat()
    print(f"Restoring sheet assignments for date: {today_utc} UTC")
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        sys.exit(1)
        
    # Ambil semua data URL terverifikasi hari ini dari DB beserta tab sheet-nya
    cursor.execute("""
        SELECT u.id, u.task_id, u.payment_url, u.status, u.verified_by, t.sheet_tab 
        FROM sheet_urls u 
        JOIN tasks t ON u.task_id = t.task_id
        WHERE u.date = %s AND u.status NOT IN ('PENDING', 'PROCESSING')
    """, (today_utc,))
    rows = cursor.fetchall()
    
    print(f"Found {len(rows)} verified URLs in database for today.")
    
    restored_count = 0
    for row in rows:
        doc_id, task_id, payment_url, status, verified_by_id, tab = row
        if not verified_by_id:
            print(f"Skipping (no verifier ID): {payment_url}")
            continue
            
        # Dapatkan info username/nama lengkap staf dari database
        cursor.execute("SELECT username, full_name FROM users WHERE user_id = %s", (int(verified_by_id),))
        user_row = cursor.fetchone()
        
        staff_str = "System-Restore"
        if user_row:
            username, full_name = user_row
            staff_str = f"@{username}" if username else (full_name if full_name else str(verified_by_id))
            
        print(f"Processing URL: {payment_url} -> Verified by: {staff_str} (Status: {status})")
        
        try:
            # 1. Tulis ulang info ASSIGNED ke Kolom F (Status) dan Kolom G (Assigned By)
            await update_sheet_status(payment_url, f"ASSIGNED - {staff_str}", tab_name=tab, staff_info=staff_str)
            # 2. Tulis ulang status final ke Kolom F (Status) dan Kolom H (Verified By)
            await update_sheet_status(payment_url, status, tab_name=tab, staff_info=staff_str)
            print("   ✅ Reconstructed columns G and H.")
            restored_count += 1
        except Exception as e:
            print(f"   ❌ Failed to restore status: {e}")
            
    cursor.close()
    conn.close()
    print(f"\nFinished. Successfully restored {restored_count} URLs in Google Sheets.")

if __name__ == "__main__":
    asyncio.run(main())
