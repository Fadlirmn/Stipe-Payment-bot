import os
import pytz
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

# Load env variables
load_dotenv()

PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB = os.getenv("POSTGRES_DB", "stripe_verif")
PG_USER = os.getenv("POSTGRES_USER", "postgres")
PG_PWD = os.getenv("POSTGRES_PASSWORD", "postgres")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Jakarta")

TZ = pytz.timezone(TIMEZONE)
today_str = datetime.now(TZ).date().isoformat()

def reset_today():
    print(f"Connecting to PostgreSQL database: {PG_DB} on {PG_HOST}...")
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DB,
            user=PG_USER,
            password=PG_PWD
        )
        cursor = conn.cursor()
        
        print(f"Purging data for date: {today_str}")
        
        # Delete sheet_urls for today
        cursor.execute("DELETE FROM sheet_urls WHERE date = %s", (today_str,))
        urls_deleted = cursor.rowcount
        
        # Delete task_progress for today
        cursor.execute("DELETE FROM task_progress WHERE date = %s", (today_str,))
        progress_deleted = cursor.rowcount
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"Successfully deleted {urls_deleted} rows from sheet_urls.")
        print(f"Successfully deleted {progress_deleted} rows from task_progress.")
        print("Done! You can now run the sync command again.")
        
    except Exception as e:
        print(f"Error resetting database: {e}")

if __name__ == "__main__":
    reset_today()
