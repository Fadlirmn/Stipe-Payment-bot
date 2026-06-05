"""
utils/formatters.py — Teks & progress bar helpers
"""
from datetime import datetime
from bot.config import TZ


def progress_bar(current: int, total: int, width: int = 10) -> str:
    """Render progress bar. Contoh: ████░░░░░░ 4/10 (40%)"""
    if total == 0:
        return "─" * width + " 0/0"
    ratio  = min(current / total, 1.0)
    filled = int(ratio * width)
    bar    = "█" * filled + "░" * (width - filled)
    pct    = int(ratio * 100)
    return f"{bar} {current}/{total} ({pct}%)"


def now_wib() -> datetime:
    return datetime.now(TZ)


def format_date_id(dt: datetime) -> str:
    """Kamis, 05 Juni 2026"""
    DAYS = ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"]
    MONTHS = ["","Januari","Februari","Maret","April","Mei","Juni",
               "Juli","Agustus","September","Oktober","November","Desember"]
    return f"{DAYS[dt.weekday()]}, {dt.day:02d} {MONTHS[dt.month]} {dt.year}"


def status_badge(status: str) -> str:
    return {
        "PENDING":    "⚪ Pending",
        "OK":         "🟢 Valid",
        "FORMAT_ERR": "🔴 Format Error",
        "DOMAIN_ERR": "🔴 Domain Error",
        "HTTP_ERR":   "🟡 HTTP Error",
        "TIMEOUT":    "🟡 Timeout",
    }.get(status, f"❓ {status}")


def task_status_badge(status: str) -> str:
    return {
        "active":    "🟢 Aktif",
        "paused":    "⏸️ Dijeda",
        "completed": "✅ Selesai",
        "archived":  "📦 Diarsipkan",
    }.get(status, status)


def role_badge(role: str) -> str:
    return {
        "dev":     "🔧 Dev",
        "admin":   "🛡️ Admin",
        "staff":   "👤 Staff",
        "pending": "⏳ Pending",
    }.get(role, role)
