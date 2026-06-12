"""
config.py — Central configuration loader
"""
import os
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

load_dotenv()

# ── Telegram ──────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DEV_IDS: list[int] = [
    int(x.strip()) for x in os.getenv("DEV_IDS", "").split(",") if x.strip()
]

# ── Google Apps Script (pengganti Google Sheets API) ────────
APPS_SCRIPT_URL: str = os.getenv("APPS_SCRIPT_URL", "")

# ── Timezone ──────────────────────────────────────────────
TZ_NAME: str = os.getenv("TIMEZONE", "Asia/Jakarta")
TZ = ZoneInfo(TZ_NAME)

# ── URL Verifier ──────────────────────────────────────────
STRIPE_ALLOWED_DOMAINS = [
    "stripe.com",
    "checkout.stripe.com",
    "buy.stripe.com",
    "billing.stripe.com",
    "invoice.stripe.com",
    "pay.stripe.com",
]
HTTP_TIMEOUT: float = 30.0

SHEET_DATE_COLUMN = "Date"
SHEET_URL_COLUMN  = "Payment URL"
SHEET_ACC_COLUMN  = "Account"
SHEET_NOTE_COLUMN = "Notes"

# ── Dashboard URL ─────────────────────────────────────────
DASHBOARD_URL: str = os.getenv("DASHBOARD_URL", "https://stipe-payment-bot.vercel.app/")

LEONARDO_PROXY_URL: str | None = os.getenv("PROXY_URL") or os.getenv("RESIDENTIAL_PROXY_URL") or None



