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


def _normalize_status(status: str) -> str:
    """Normalisasi status ke canonical value. SUCCESS → OK."""
    s = status.strip().upper()
    if s == "SUCCESS":
        return "OK"
    return s


def _is_ok_status(status: str | None) -> bool:
    """Cek apakah status termasuk OK (termasuk legacy SUCCESS)."""
    return status in ("OK", "SUCCESS")


# ── Public API ────────────────────────────────────────────

async def fetch_today_urls(tab_name: str = "Sheet1", target_date: Optional[date] = None, all_rows: bool = False) -> list[dict]:
    """
    Mengambil semua baris dari Google Sheet via Apps Script Web App
    yang kolom Date-nya cocok dengan `target_date` (default: hari ini).

    Mengembalikan list of dict:
        [{ "account": str, "payment_url": str, "notes": str }, ...]
    """
    today = target_date or datetime.now(TZ).date()
    date_str = today.strftime("%Y-%m-%d")

    logger.info(f"[SheetParser] Fetching via Apps Script: date={date_str}, tab={tab_name}, all_rows={all_rows}")

    if not APPS_SCRIPT_URL:
        raise RuntimeError("APPS_SCRIPT_URL belum diset di .env")

    params = {
        "date": date_str,
        "tab":  tab_name,
    }
    if all_rows:
        params["all"] = "1"

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
            "assigned_by": str(item.get("assigned_by", "")).strip(),
            "verified_by": str(item.get("verified_by", "")).strip(),
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


async def reconcile_and_verify_failed_urls(target_date_str: str, actor_id: Optional[int] = None, progress_callback = None) -> dict:
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
    from bot.services.url_verifier import verify_url, check_leonardo_api_key, verify_stripe_and_credits, VerifResult, VerifStatus
    from bot.utils.formatters import now_wib
    import asyncio

    logger.info(f"[Reconciler] Memulai rekonsiliasi & re-verifikasi untuk tanggal {target_date_str}")

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
            rows = await fetch_today_urls(tab_name=tab, target_date=date.fromisoformat(target_date_str))
            for r in rows:
                sheet_pending_urls.add(r["payment_url"].strip())
        except Exception as e:
            logger.error(f"[Reconciler] Gagal fetch tab '{tab}' dari Sheets: {e}")
            raise RuntimeError(f"Gagal memanggil Google Sheets untuk tab '{tab}': {e}")

    # 3. Ambil URL failed dari DB
    failed_urls = await fdb.get_all_failed_urls(date_str=target_date_str)
    if not failed_urls:
        logger.info(f"[Reconciler] Tidak ada URL gagal di DB untuk tanggal {target_date_str}")
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
    processed_count = 0

    async def re_verify_one(url_obj: dict):
        nonlocal reverif_ok, reverif_fail, processed_count
        payment_url = url_obj["payment_url"]
        doc_id      = url_obj["id"]
        task_id     = url_obj["task_id"]
        tab         = task_tab_map.get(task_id, "Sheet1")
        api_key     = url_obj.get("api_key", "")

        async with sem:
            try:
                result, api_key_status = await verify_stripe_and_credits(payment_url, api_key)

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
            finally:
                processed_count += 1
                if progress_callback:
                    await progress_callback(processed_count, len(need_reverif))

    if need_reverif:
        await asyncio.gather(*(re_verify_one(u) for u in need_reverif), return_exceptions=True)

    logger.info(
        f"[Reconciler] Selesai rekonsiliasi & re-verifikasi untuk {target_date_str}. "
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


async def verify_all_urls_today(target_date_str: str, actor_id: int, progress_callback=None) -> dict:
    """
    Verifikasi SEMUA URL hari ini di DB, lalu update hasilnya ke DB dan Google Sheets.
    """
    import bot.db as fdb
    from bot.services.url_verifier import verify_stripe_and_credits
    from bot.utils.formatters import now_wib
    import asyncio

    logger.info(f"[VerifyAll] Memulai verifikasi masal hari ini untuk tanggal {target_date_str}")

    # 1. Ambil semua task aktif
    all_tasks = await fdb.list_tasks()
    task_tab_map = {t["id"]: t.get("sheet_tab", "Sheet1") for t in all_tasks}

    # 2. Ambil semua URL hari ini dari DB
    all_urls = []
    for task in all_tasks:
        task_id = task["id"]
        urls, _ = await fdb.list_sheet_urls(task_id=task_id, date=target_date_str, limit=1000)
        for u in urls:
            u["_tab"] = task_tab_map.get(task_id, "Sheet1")
        all_urls.extend(urls)

    if not all_urls:
        return {"total": 0, "ok": 0, "fail": 0}

    # Ambil info actor
    actor_str = "Admin-VerifyAll"
    try:
        actor_user = await fdb.get_user(actor_id)
        if actor_user:
            username = actor_user.get("username")
            full_name = actor_user.get("full_name")
            actor_str = f"@{username}" if username else (full_name if full_name else str(actor_id))
    except Exception:
        pass

    sem = asyncio.Semaphore(5)
    total_count = len(all_urls)
    processed_count = 0
    ok_count = 0
    fail_count = 0

    async def verify_one(url_obj: dict):
        nonlocal processed_count, ok_count, fail_count
        payment_url = url_obj["payment_url"]
        doc_id      = url_obj["id"]
        tab         = url_obj["_tab"]
        api_key     = url_obj.get("api_key", "")

        # Pertahankan verifikator/assignee asli agar kontribusi staf tidak hilang
        original_verifier = url_obj.get("verified_by")
        target_verifier = original_verifier if original_verifier else str(actor_id)
        
        try:
            target_verifier_id = int(target_verifier)
        except (ValueError, TypeError):
            target_verifier_id = actor_id

        async with sem:
            try:
                # Lakukan verifikasi terpadu
                result, api_key_status = await verify_stripe_and_credits(payment_url, api_key)

                # Update ke database
                db_update = {
                    "status":      result.status.value,
                    "http_code":   result.http_code,
                    "error_msg":   result.message if not result.is_ok else None,
                    "verified_by": str(target_verifier_id),
                    "verified_at": now_wib().isoformat(),
                }
                if api_key:
                    db_update["api_key_status"] = api_key_status
                await fdb.update_sheet_url(doc_id, **db_update)

                # Catat progress delta kontribusi staf
                old_status = url_obj.get("status")
                new_status = result.status.value
                if old_status != new_status:
                    submitted_delta = 0
                    ok_delta = 1 if _is_ok_status(new_status) else 0
                    fail_delta = 1 if not _is_ok_status(new_status) else 0
                    if _is_ok_status(old_status):
                        ok_delta -= 1
                    elif old_status not in ("PENDING", "PROCESSING", None):
                        fail_delta -= 1
                    
                    try:
                        await fdb.upsert_progress(
                            task_id=url_obj["task_id"], user_id=target_verifier_id,
                            date=url_obj["date"],
                            submitted_delta=submitted_delta, ok_delta=ok_delta, fail_delta=fail_delta
                        )
                    except Exception as e:
                        logger.error(f"[VerifyAll] Gagal update progress untuk user {target_verifier_id}: {e}")

                # Update ke Google Sheets (Tulis verifikator asli ke Sheets jika ada, jika tidak gunakan actor_str)
                try:
                    sheet_staff_info = actor_str
                    if original_verifier:
                        try:
                            orig_user = await fdb.get_user(int(original_verifier))
                            if orig_user:
                                username = orig_user.get("username")
                                full_name = orig_user.get("full_name")
                                sheet_staff_info = f"@{username}" if username else (full_name if full_name else str(original_verifier))
                        except Exception:
                            pass
                    await update_sheet_status(payment_url, result.status.value, tab_name=tab, staff_info=sheet_staff_info)
                except Exception as e:
                    logger.warning(f"[VerifyAll] Gagal update status Sheets untuk {payment_url}: {e}")

                if result.is_ok:
                    ok_count += 1
                else:
                    fail_count += 1

            except Exception as ex:
                logger.error(f"[VerifyAll] Error memproses {payment_url}: {ex}")
                fail_count += 1
            finally:
                processed_count += 1
                if progress_callback:
                    await progress_callback(processed_count, total_count)

    await asyncio.gather(*(verify_one(u) for u in all_urls), return_exceptions=True)

    return {
        "total": total_count,
        "ok": ok_count,
        "fail": fail_count
    }


async def resolve_user_id_by_string(staff_str: str) -> Optional[int]:
    if not staff_str:
        return None
    staff_str = staff_str.strip()
    if staff_str.isdigit():
        return int(staff_str)
    
    # Bersihkan nama pengguna (buang karakter @ di awal jika ada)
    uname = staff_str
    if uname.startswith("@"):
        uname = uname[1:]
        
    import bot.db as fdb
    # Cek kecocokan username secara langsung
    user = await fdb.get_user_by_username(uname)
    if user:
        return user["user_id"]
        
    # Cek case-insensitive username / full_name dengan list_users
    users = await fdb.list_users()
    for u in users:
        u_name = u.get("username")
        if u_name and u_name.lower() == uname.lower():
            return u["user_id"]
        f_name = u.get("full_name")
        if f_name and f_name.lower() == staff_str.lower():
            return u["user_id"]
            
    return None


async def sync_status_from_sheets_to_db(target_date_str: str, progress_callback=None) -> dict:
    """
    Sinkronisasi status hasil akhir verifikasi (Kolom G) dan verifikator (Kolom H)
    dari Google Sheets kembali ke database PostgreSQL, serta memperbarui task_progress.
    """
    import bot.db as fdb
    from bot.utils.formatters import now_wib
    import asyncio
    import hashlib
    from datetime import date

    logger.info(f"[SyncStatus] Memulai sinkronisasi status Sheets -> DB untuk tanggal {target_date_str}")

    # 1. Ambil semua task aktif
    all_tasks = await fdb.list_tasks()
    
    total_processed = 0
    updated_count = 0
    errors = []

    for task in all_tasks:
        task_id = task["id"]
        tab = task.get("sheet_tab", "Sheet1")
        
        try:
            # Panggil fetch_today_urls dengan all_rows=True untuk mengambil seluruh baris (termasuk yang final)
            rows = await fetch_today_urls(tab_name=tab, target_date=date.fromisoformat(target_date_str), all_rows=True)
        except Exception as e:
            logger.error(f"[SyncStatus] Gagal fetch tab '{tab}' dari Sheets: {e}")
            errors.append(f"Tab '{tab}': {e}")
            continue

        if not rows:
            continue

        for row in rows:
            total_processed += 1
            payment_url = row["payment_url"]
            sheet_status = row["status"]
            verified_by_str = row.get("verified_by", "")
            assigned_by_str = row.get("assigned_by", "")
            
            # Cari di DB
            doc_id = hashlib.md5(f"{task_id}_{payment_url}".encode("utf-8")).hexdigest()
            db_url = await fdb.get_sheet_url(doc_id)
            
            # Jika tidak ada di DB, kita insert sebagai URL baru
            if not db_url:
                try:
                    await fdb.add_sheet_url(
                        task_id=task_id,
                        date=target_date_str,
                        account=row["account"],
                        payment_url=payment_url,
                        notes=row["notes"],
                        api_key=row.get("api_key", ""),
                        check_exists=False
                    )
                    db_url = await fdb.get_sheet_url(doc_id)
                except Exception as e:
                    logger.error(f"[SyncStatus] Gagal insert URL baru {payment_url}: {e}")
                    continue

            # Tentukan verifikator
            target_verifier_id = None
            
            # 1. Cari dari kolom H (Verified By)
            if verified_by_str:
                target_verifier_id = await resolve_user_id_by_string(verified_by_str)
            
            # 2. Cari dari kolom F (Assigned By) jika verifikator kosong
            if not target_verifier_id and assigned_by_str:
                target_verifier_id = await resolve_user_id_by_string(assigned_by_str)
                
            # 3. Gunakan verifikator di DB jika ada
            if not target_verifier_id and db_url.get("verified_by"):
                try:
                    target_verifier_id = int(db_url["verified_by"])
                except (ValueError, TypeError):
                    pass

            old_status = db_url.get("status")
            new_status = _normalize_status(sheet_status)  # SUCCESS → OK
            
            # Jika status berbeda dan new_status tidak kosong
            if new_status and new_status != old_status:
                is_final_status = _is_ok_status(new_status) or new_status.startswith("HTTP_ERR") or new_status in ("FAILED", "TIMEOUT", "SKIPPED", "ERROR")
                
                # Update DB sheet_urls
                db_update = {
                    "status": new_status,
                    "verified_at": now_wib().isoformat()
                }
                if target_verifier_id:
                    db_update["verified_by"] = str(target_verifier_id)
                await fdb.update_sheet_url(doc_id, **db_update)
                updated_count += 1

                # Jika status baru adalah status final dan verifikator teridentifikasi, update progress
                if is_final_status and target_verifier_id:
                    submitted_delta = 0
                    ok_delta = 0
                    fail_delta = 0
                    
                    # Jika status sebelumnya adalah PENDING atau PROCESSING (belum final)
                    if old_status in ("PENDING", "PROCESSING", None):
                        submitted_delta = 1
                        if _is_ok_status(new_status):
                            ok_delta = 1
                        else:
                            fail_delta = 1
                    else:
                        # Jika sebelumnya sudah status final, sesuaikan deltas
                        if _is_ok_status(new_status):
                            ok_delta = 1
                        else:
                            fail_delta = 1
                            
                        if _is_ok_status(old_status):
                            ok_delta -= 1
                        else:
                            fail_delta -= 1
                            
                    try:
                        await fdb.upsert_progress(
                            task_id=task_id,
                            user_id=target_verifier_id,
                            date=target_date_str,
                            submitted_delta=submitted_delta,
                            ok_delta=ok_delta,
                            fail_delta=fail_delta
                        )
                    except Exception as e:
                        logger.error(f"[SyncStatus] Gagal update progress untuk user {target_verifier_id}: {e}")

            if progress_callback:
                await progress_callback(total_processed)

    return {
        "processed": total_processed,
        "updated": updated_count,
        "errors": errors
    }



