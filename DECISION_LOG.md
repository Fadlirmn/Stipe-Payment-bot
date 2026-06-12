# Decision Log

## [2026-06-12] - Leonardo API Key Credits Verification & Proxy Integration

### Context
1. User meminta bot melakukan pengecekan kredit/token API Key Leonardo.ai dengan menjumlahkan `subscriptionTokens` + `paidTokens` + `apiPaidTokens` mengacu pada implementasi `Generative-Leo`.
2. Jika Stripe URL error (tanda sudah dibayar/expired) ATAU kredit API Key > 0, status akhir verifikasi adalah sukses (OK). Selain itu, status akhir verifikasi dianggap gagal (FAIL).
3. Dibutuhkan proxy dinamis yang bisa dirotasi per request untuk menghindari ban/rate limit saat memanggil endpoint Leonardo.ai.

### Decisions
1. **Penyatuan Logika Verifikasi Terpadu**:
   - *Decision*: Membuat fungsi pembungkus `verify_stripe_and_credits` di `url_verifier.py` yang menggabungkan hasil verifikasi Stripe dan status token Leonardo API Key.
   - *Rationale*: Meminimalisir duplikasi kode karena logika verifikasi ini dipanggil di 4 tempat berbeda di dalam bot.
2. **Kalkulasi Sisa Kredit Akurat**:
   - *Decision*: Mengambil dan menjumlahkan `subscriptionTokens` + `paidTokens` + `apiPaidTokens` dari object `user_details[0]` respons API Leonardo.
   - *Rationale*: Mengikuti standar yang sudah teruji di repositori `Generative-Leo` milik user.
3. **Penerapan Rotated Proxy per Request**:
   - *Decision*: Menggunakan helper `get_rotated_proxy_url` untuk mem-parsing variable `.env` (`PROXY_URL` atau `RESIDENTIAL_PROXY_URL`). Jika terdeteksi URL API Croxy, bot memanggil API tersebut untuk mendapatkan IP:Port dinamis terbaru dan membuat client `httpx.AsyncClient` ad-hoc untuk request tersebut.
   - *Rationale*: Mencegah IP server bot terblokir karena membuat request berulang ke API Leonardo secara bersamaan.

## [2026-06-12] - Reconcile & Re-verify Failed URLs, Menu Cleanup, and Bugfixes

### Context
1. Telegram callback data length is limited to 64 bytes, causing crashes on retry clicks when using long task IDs.
2. `NameError` on `logger` caused crashes during admin actions when an error occurred.
3. Backup/restore manual options are no longer desired in the Telegram UI.
4. Need periodic auto-verification of failed URLs referencing status changes in Google Sheets (reconciliation).

### Decisions
1. **Shorten Retry Callback Data**:
   - *Decision*: Remove `task_id` from the `callback_data` payload for retry actions and load it dynamically from the database using `doc_id`.
   - *Rationale*: Keeps the payload length ~45 characters (safely below 64-byte limit) while maintaining exact query capabilities.
2. Periodic Re-verification Job:
   - *Decision*: Set up a background job `job_auto_verify_failed` in `scheduler.py` running every 15 minutes.
   - *Rationale*: Periodically reconciles local failed URLs with active Google Sheets status to sync updates automatically.
3. Timeout & Error Propagation in Reconciliation:
   - *Decision*: Raise an exception immediately and fail the reconciler if Google Sheets fetch fails, and increase `HTTP_TIMEOUT` to 30.0 seconds.
   - *Rationale*: Prevents database corruption (all database fails incorrectly marked OK when Sheets query times out) and allows slow Apps Script calls to complete safely.
4. Pembersihan Menu DevTools:
   - *Decision*: Remove Backup and Restore buttons from the inline keyboard `cb_menu_devtools`.
   - *Rationale*: Clean up UI options as requested by the user.
5. Fix NameError and Logger:
   - *Decision*: Import `logger` from `loguru` in `bot/handlers/admin.py`.
   - *Rationale*: Prevents crashes when errors/warnings are being logged in admin callbacks.
6. Pengecekan Kredit API Key:
   - *Decision*: Parse response from Leonardo.ai and verify that both `apiCreditBalance` and `subscriptionTokens` are greater than 0.
   - *Rationale*: Prevents keys with 0 credits from being mistakenly treated as ACTIVE, ensuring they are marked as EXPIRED instead.
7. Penghapusan Tombol Push Status:
   - *Decision*: Remove **Push Status → Sheet** button from the devtools keyboard.
   - *Rationale*: Keeps UI clean and prevents redundant manual pushes.

---

## [2026-06-12] - Task Quota Sync Implementation

### Context
When the task quota is changed, the pre-assigned pending links for users today become out of sync, locking them for users who can no longer verify them.

### Decisions
1. **Link Assignment Synchronization**:
   - *Decision*: If `quota_per_staff` is increased, dynamically assign additional `PENDING` URLs from the database pool to active staff members. If decreased, retain all existing assigned URLs ("sisa perubahan task sebelumnya").
   - *Rationale*: Allows users to keep verifying already assigned work while adjusting future capacity correctly.
2. **Google Sheets Sync**:
   - *Decision*: Call `update_sheet_status` to mark new allocations as `"ASSIGNED"` when quota is increased.
3. **HTML / Redirect Status Check**:
   - *Decision*: Check HTML content for payment completion phrases (e.g. "already completed") and detect success redirects away from Stripe domains.
   - *Rationale*: Prevents false positives where unpaid checkout pages returned a HTTP 200 and were wrongly validated.
4. **Optimized Client Pooling**:
   - *Decision*: Initialize a single global `httpx.AsyncClient` in `url_verifier.py`.
   - *Rationale*: Reuse TCP connections to handle high concurrency from multiple concurrent staff verification requests.
5. **Exemption of Admins & Devs from Staff Quotas**:
   - *Decision*: Bypass the `quota_exceeded` checks when rendering the verification button for users with admin or dev roles.
   - *Rationale*: Admins and developers must be able to perform manual verification or overrides even if the regular staff quota limit has been reached.
6. **Concurrency Limiting in Bulk Operations**:
   - *Decision*: Apply `asyncio.Semaphore(5)` to `cb_url_verify_all` to limit concurrent requests.
   - *Rationale*: Prevents hitting API rate limits or triggering security/anti-bot blocks when staff members trigger bulk checks simultaneously.
7. **Admin Re-Verification Key Synchronization**:
   - *Decision*: Check Leonardo API keys in `re_verify_one` if they are present, rather than checking Stripe URLs only.
   - *Rationale*: Makes sure admin re-verifications use the exact same logic as staff verifications for maximum reliability.
8. **Compatibility Mapping of Task IDs**:
   - *Decision*: Automatically map `task_id` value to `id` key in `postgres_list_tasks`, `sqlite_list_tasks`, and `sqlite_get_task` query results.
   - *Rationale*: Prevents `KeyError: 'id'` crashes in handlers (like `/verify_failed` and `/sync_sheets`) which access `t["id"]` on returned task list row dicts.
9. **Return Type Consistency for `ensure_quota_synced`**:
    - *Decision*: Ubah return type dari `int` (count) menjadi `list[dict]` (URL objects yang baru di-assign).
    - *Rationale*: Caller di `_show_url_list` mengiterasi return value untuk update status ke Google Sheets per-URL. Mengembalikan `int` menyebabkan `TypeError: 'int' object is not iterable` yang membuat bot crash saat staff membuka daftar link.




