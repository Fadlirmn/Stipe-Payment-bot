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

async def fetch_today_urls(tab_name: str = "Sheet1", target_date: Optional[date] = None) -> list[dict]:
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
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(APPS_SCRIPT_URL, params=params)
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
            "api_key":     str(item.get("api_key", "")).strip(),
            "payment_url": url,
            "notes":       str(item.get("notes", "")).strip(),
            "status":      str(item.get("status", "")).strip(),
            "date":        str(item.get("date", "")).strip(),
            "timestamp":   str(item.get("timestamp", "")).strip(),
        })

    logger.info(f"[SheetParser] {len(results)} URL valid untuk tanggal {today}")
    return results


async def update_sheet_status(stripe_url: str, status: str, tab_name: str = "Sheet1", staff_info: Optional[str] = None) -> bool:
    """
    Mengupdate status baris di Google Sheet via Apps Script Web App (doPost).
    """
    if not APPS_SCRIPT_URL:
        logger.warning("[SheetParser] APPS_SCRIPT_URL belum diset, skip update_sheet_status")
        return False

    payload = {
        "action": "updateStatus",
        "stripe_url": stripe_url,
        "status": status,
        "tab": tab_name
    }
    if staff_info is not None:
        payload["staff_info"] = staff_info

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.post(APPS_SCRIPT_URL, json=payload)
            resp.raise_for_status()
            res_json = resp.json()
            logger.info(f"[SheetParser] Update status Sheet: url={stripe_url}, status={status}, staff={staff_info}, resp={res_json}")
            return res_json.get("status") == "updated"
    except Exception as exc:
        logger.error(f"[SheetParser] Gagal memanggil Apps Script updateStatus: {exc}")
        return False


async def reconcile_and_verify_failed_urls(target_date_utc: str, actor_id: Optional[int] = None) -> dict:
    """
    Melakukan verifikasi ulang terhadap URL yang gagal di database dengan mengacu pada Google Sheets.
    Jika URL gagal di DB ternyata sudah tidak ada di baris pending Google Sheets (artinya sudah sukses/OK di Sheets),
    maka status di DB di-update menjadi OK (reconciled).
    Jika masih ada di Google Sheets, maka dilakukan re-verifikasi secara berkala.
    
    Mengembalikan dict rangkuman hasil:
    {
        "already_done_count": int,
        "sync_ok_count": int,
        "reverif_ok": int,
        "reverif_fail": int,
        "total_failed": int
    }
    """
    import bot.db as fdb
    from bot.services.url_verifier import verify_url, check_leonardo_api_key, VerifResult, VerifStatus
    from bot.utils.formatters import now_wib
    import asyncio

    logger.info(f"[Reconciler] Memulai rekonsiliasi & re-verifikasi untuk tanggal {target_date_utc} UTC")

    # 1. Ambil semua task aktif
    all_tasks = await fdb.list_tasks()
    task_tab_map = {t["id"]: t.get("sheet_tab", "Sheet1") for t in all_tasks}

    # 2. Ambil pending URLs dari Google Sheets (untuk semua tab aktif)
    sheet_pending_urls = set()
    tabs_seen = set()
    for task in all_tasks:
        tab = task.get("sheet_tab", "Sheet1")
        if tab in tabs_seen:
            continue
        tabs_seen.add(tab)
        try:
            # fetch_today_urls mengembalikan baris yang belum final status
            rows = await fetch_today_urls(tab_name=tab, target_date=date.fromisoformat(target_date_utc))
            for r in rows:
                sheet_pending_urls.add(r["payment_url"].strip())
        except Exception as e:
            logger.error(f"[Reconciler] Gagal fetch tab '{tab}' dari Sheets: {e}")
            raise RuntimeError(f"Gagal memanggil Google Sheets untuk tab '{tab}': {e}")

    # 3. Ambil URL failed dari DB
    failed_urls = await fdb.get_all_failed_urls(date_str=target_date_utc)
    if not failed_urls:
        logger.info(f"[Reconciler] Tidak ada URL gagal di DB untuk tanggal {target_date_utc}")
        return {
            "already_done_count": 0,
            "sync_ok_count": 0,
            "reverif_ok": 0,
            "reverif_fail": 0,
            "total_failed": 0
        }

    # Pisahkan URL
    already_done = []
    need_reverif = []
    for u in failed_urls:
        purl = u.get("payment_url", "").strip()
        if purl and purl not in sheet_pending_urls:
            already_done.append(u)
        else:
            need_reverif.append(u)

    # 4. Update DB untuk yang sudah disubmit di Sheets -> reset ke OK
    sync_ok_count = 0
    for u in already_done:
        try:
            await fdb.update_sheet_url(u["id"], status="OK", error_msg=None,
                                       verified_at=now_wib().isoformat())
            sync_ok_count += 1
        except Exception as e:
            logger.warning(f"[Reconciler] Gagal sync-reset {u['payment_url']}: {e}")

    # 5. Re-verifikasi yang masih pending
    sem = asyncio.Semaphore(5)
    reverif_ok = 0
    reverif_fail = 0

    async def re_verify_one(url_obj: dict):
        nonlocal reverif_ok, reverif_fail
        payment_url = url_obj["payment_url"]
        doc_id      = url_obj["id"]
        task_id     = url_obj["task_id"]
        tab         = task_tab_map.get(task_id, "Sheet1")
        api_key     = url_obj.get("api_key", "")

        async with sem:
            try:
                api_key_status = None
                if api_key:
                    api_key_status = await check_leonardo_api_key(api_key)
                    if api_key_status == "ACTIVE":
                        result = VerifResult(
                            status=VerifStatus.OK,
                            http_code=200,
                            message="Leonardo API Key Aktif -> Pembayaran Terkonfirmasi ✅",
                            url=payment_url
                        )
                    elif api_key_status == "EXPIRED":
                        result = VerifResult(
                            status=VerifStatus.HTTP_ERR,
                            http_code=401,
                            message="Leonardo API Key Expired/Unverified -> Stripe Belum Dibayar ❌",
                            url=payment_url
                        )
                    else:
                        result = await verify_url(payment_url)
                else:
                    result = await verify_url(payment_url)

                db_update = {
                    "status":      result.status.value,
                    "http_code":   result.http_code,
                    "error_msg":   result.message if not result.is_ok else None,
                    "verified_at": now_wib().isoformat(),
                }
                if api_key:
                    db_update["api_key_status"] = api_key_status
                await fdb.update_sheet_url(doc_id, **db_update)

                try:
                    await update_sheet_status(
                        payment_url, result.status.value,
                        tab_name=tab, staff_info="System-AutoReVerify"
                    )
                except Exception as e:
                    logger.error(f"[Reconciler] Gagal update Sheet untuk {payment_url}: {e}")

                if actor_id:
                    await fdb.add_audit_log(
                        actor_id=actor_id, action="url.reverify",
                        target_type="sheet_url", target_id=doc_id,
                        detail={"url": payment_url, "status": result.status.value,
                                "http_code": result.http_code},
                    )

                if result.is_ok:
                    reverif_ok += 1
                    if url_obj.get("verified_by"):
                        try:
                            staff_id = int(url_obj["verified_by"])
                            await fdb.upsert_progress(
                                task_id=task_id, user_id=staff_id,
                                date=url_obj["date"],
                                submitted_delta=0, ok_delta=1, fail_delta=-1
                            )
                        except Exception as e:
                            logger.error(f"[Reconciler] Gagal update progress: {e}")
                else:
                    reverif_fail += 1

            except Exception as ex:
                logger.error(f"[Reconciler] Error memproses {payment_url}: {ex}")
                reverif_fail += 1

    if need_reverif:
        await asyncio.gather(*(re_verify_one(u) for u in need_reverif), return_exceptions=True)

    logger.info(
        f"[Reconciler] Selesai rekonsiliasi & re-verifikasi untuk {target_date_utc}. "
        f"Already done: {len(already_done)}, Synced to OK: {sync_ok_count}, "
        f"Re-verified OK: {reverif_ok}, Re-verified Fail: {reverif_fail}"
    )

    return {
        "already_done_count": len(already_done),
        "sync_ok_count": sync_ok_count,
        "reverif_ok": reverif_ok,
        "reverif_fail": reverif_fail,
        "total_failed": len(failed_urls)
    }


