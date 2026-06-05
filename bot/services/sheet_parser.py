"""
services/sheet_parser.py
Mengambil URL Payment Stripe via Google Apps Script Web App.
Tidak memerlukan Service Account, credentials.json, atau API key apapun.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

import httpx
from loguru import logger

from bot.config import (
    APPS_SCRIPT_URL,
    SHEET_DATE_COLUMN,
    SHEET_URL_COLUMN,
    SHEET_ACC_COLUMN,
    SHEET_NOTE_COLUMN,
    TZ,
    HTTP_TIMEOUT,
)


def _is_stripe_url(url: str) -> bool:
    stripe_domains = re.compile(
        r"^https?://(checkout|buy|billing|invoice|pay)?\.?stripe\.com/",
        re.IGNORECASE,
    )
    return bool(stripe_domains.match(url.strip()))


# ── Public API ────────────────────────────────────────────

def fetch_today_urls(tab_name: str = "Sheet1", target_date: Optional[date] = None) -> list[dict]:
    """
    Mengambil semua baris dari Google Sheet via Apps Script Web App
    yang kolom Date-nya cocok dengan `target_date` (default: hari ini).

    Mengembalikan list of dict:
        [{ "account": str, "payment_url": str, "notes": str }, ...]
    """
    today = target_date or datetime.now(TZ).date()
    date_str = today.strftime("%Y-%m-%d")

    logger.info(f"[SheetParser] Fetching via Apps Script: date={date_str}, tab={tab_name}")

    if not APPS_SCRIPT_URL:
        raise RuntimeError("APPS_SCRIPT_URL belum diset di .env")

    params = {
        "date": date_str,
        "tab":  tab_name,
    }

    try:
        resp = httpx.get(APPS_SCRIPT_URL, params=params, timeout=HTTP_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.error(f"[SheetParser] Gagal memanggil Apps Script: {exc}")
        raise

    if "error" in payload:
        raise RuntimeError(f"[SheetParser] Apps Script error: {payload['error']}")

    raw_data: list[dict] = payload.get("data", [])
    logger.info(f"[SheetParser] {len(raw_data)} baris diterima dari Apps Script")

    results: list[dict] = []
    for item in raw_data:
        url = str(item.get("payment_url", "")).strip()
        if not url:
            continue
        if not _is_stripe_url(url):
            logger.warning(f"[SheetParser] URL bukan domain Stripe, skip → {url}")
            continue
        results.append({
            "account":     str(item.get("account", "")).strip(),
            "payment_url": url,
            "notes":       str(item.get("notes", "")).strip(),
        })

    logger.info(f"[SheetParser] {len(results)} URL valid untuk tanggal {today}")
    return results
