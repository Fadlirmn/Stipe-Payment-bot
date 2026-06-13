# Decision Log

## [2026-06-13] - Prevent Status Reset in Sheets -> DB Sync

### Context
When syncing status back from Google Sheets to the Database (via `sync_status_from_sheets_to_db`), if a URL was already verified and had a final/verified status (like `OK`, `FAILED`, etc.) in the database, but the spreadsheet had not been updated yet or was restored (e.g., having status `PENDING` or `ASSIGNED`), the DB status would get overwritten and reset back to the non-final status.

### Decisions
1. **Prevent Demotion of Final Statuses**: Modify `sync_status_from_sheets_to_db` to check if the database status is already a final status (`OK`, `FAILED`, `TIMEOUT`, `SKIPPED`, `ERROR`, or starting with `HTTP_ERR`). If it is, and the incoming status from the sheet is not a final status (like `PENDING` or `ASSIGNED`), prevent overwriting the DB.
2. **Allow Final-to-Final Updates**: Allow updates if both the DB status and the sheet status are final (e.g., `FAILED` -> `OK`), in case manual corrections are made in the spreadsheet.

### Affected Files
- `bot/services/sheet_parser.py`

## [2026-06-13] - Populate assigned_to on Link Claim

### Context
When staff claimed links via the bot's "Ambil Link" (get_or_claim_next_url), the database only updated `verified_by` to the claiming user, leaving `assigned_to` empty. Since dashboard statistics and bot reports were changed to group strictly by the immutable `assigned_to` field, the claimed URLs did not show up in the users' stats.

### Decisions
1. **Populate assigned_to during claims**: Update `postgres_get_or_claim_next_url` and `sqlite_get_or_claim_next_url` to set `assigned_to` using `COALESCE(assigned_to, ?)` or `COALESCE(assigned_to, %s)` whenever a link is claimed, reserved, or stolen (if it was somehow left empty).
2. **Prevent race conditions / conflicts**: Using `COALESCE` guarantees that if `assigned_to` is already populated, it will not be overwritten (preserving the original attribution even if another user helps verify the URL).

### Affected Files
- `bot/postgres_db.py`
- `bot/sqlite_db.py`

## [2026-06-13] - Reset DB before Manual Sync Sheet

### Context
When administrators or developers trigger a manual "Sync Sheet" action, they expect a fresh sync that completely reflects the current state of Google Sheets, including correcting any previously synced/assigned links if the spreadsheet was cleared or changed. Previously, manual sync only appended or updated in place, which could leave orphaned or conflicting links in the database.

### Decisions
1. **Destructive Manual Sync**: Add a `reset_task_today` helper in PostgreSQL and SQLite databases that clears the daily URLs and task progress for a given task.
2. **Auto-reset before manual pull**: Intercept manual sync callbacks (`cb_task_sync_sheet` and `_dev_action` sync) to run `reset_task_today` prior to fetching rows from Google Sheets.
3. **Preserve background sync safety**: Keep background scheduler auto-sync non-destructive (no database reset) to import newly added links incrementally without losing staff progress.

### Affected Files
- `bot/postgres_db.py`
- `bot/sqlite_db.py`
- `bot/db.py`
- `bot/handlers/admin.py`

## [2026-06-13] - Query Daily Report Metrics Directly from sheet_urls

### Context
The `/report` command (daily summary) and the End-of-Day scheduler task computed verification statistics per staff member using the `task_progress` table. Due to prior timezone and `SUCCESS`/`OK` delta counting bugs, the data in `task_progress` was corrupted, resulting in negative verified numbers (e.g., `-16✅` or `576❌`) on the Telegram report screen.

### Decisions
1. **Query raw data directly**: Modify both `cmd_report` and `job_eod_summary` to query `sheet_urls` for the current date directly.
2. **Strict Assignment Grouping**: Group/filter statistics strictly by `assigned_to` to represent who a URL was assigned to, rather than who verified it (`verified_by`).
3. **Normalized 3-Status Metric**: Standardize all metrics into three columns/categories: `Submitted` (total URLs assigned), `OK` (URLs with OK status), and `Gagal` (all non-OK statuses, replacing Pending).
4. **Completion Percentage**: Include clear `OK / task` percentage formatting (e.g. `85% (17/20)`) in both bot reports and dashboard tables.

### Affected Files
- `bot/handlers/admin.py`
- `bot/scheduler.py`
- `js/dashboard.js`
- `index.html`

## [2026-06-13] - Timezone & Status Standardization

### Context
1. Dashboard menampilkan statistik yang salah ("ngaco") — angka OK **2× lipat dari submitted** dan fail **negatif**.
2. Contoh data absurd dari Staff Monitor:

| Staff | Submitted | OK | Fail | Analisis |
|---|---|---|---|---|
| Ryu | 25 | 50 | -25 | OK = 2× submitted, Fail = -(submitted) |
| Siti Mudrika | 25 | 50 | -25 | Sama — setiap cycle menambah +1 OK, -1 Fail |
| Mia Salsabila | 25 | 41 | -16 | 16 cycle dari 25 URL |
| Mutiara | 25 | 42 | -17 | 17 cycle dari 25 URL |

### Root Cause Analysis — Mengapa Angka Bisa Absurd

Masalah ini disebabkan oleh **siklus berulang** antara 2 proses otomatis:

**Siklus Infinite Loop:**

```
┌──────────────────────────────────────────────────────────────┐
│  1. sync_status_from_sheets_to_db  (setiap 30 menit)        │
│     - Baca status dari Google Sheets                        │
│     - Sheets punya "SUCCESS" (bukan "OK")                   │
│     - Simpan ke DB TANPA normalisasi → DB = "SUCCESS"       │
│                                                              │
│  2. job_auto_verify_failed / verify_all  (setiap 15 menit)  │
│     - Baca dari DB: old_status = "SUCCESS"                  │
│     - Verifikasi ulang → new_status = "OK"                  │
│     - "SUCCESS" != "OK" → masuk blok delta counting         │
│     - ok_delta = +1 (new_status == "OK" → True)             │
│     - Cek: old_status == "OK"? → NO! (old = "SUCCESS")      │
│     - ok_delta TIDAK dikurangi → tetap +1                   │
│     - fail_delta = -1 (old bukan PENDING, bukan OK)         │
│     - Update DB → "OK"                                      │
│                                                              │
│  3. Kembali ke langkah 1 (sync baca "SUCCESS" dari Sheets)  │
│     - DB di-overwrite kembali ke "SUCCESS"                   │
│     - Kembali ke langkah 2                                  │
│     ... dst setiap 15-30 menit sepanjang hari                │
└──────────────────────────────────────────────────────────────┘
```

**Efek per siklus per URL:**
- `ok_delta += 1` (menambah OK tanpa mengurangi yang lama)
- `fail_delta -= 1` (mengurangi fail yang tidak seharusnya)

**Akumulasi dalam 1 hari (misalnya 8 jam kerja):**
- Auto-verify jalan setiap 15 menit = ~32 siklus
- Per URL: OK bertambah hingga +32, Fail turun hingga -32
- Itulah mengapa OK bisa 50 padahal submitted hanya 25 (25 asli + 25 siklus)

### Root Causes (3 bug gabungan)

1. **`sync_status_from_sheets_to_db` tidak normalisasi status** — menyimpan "SUCCESS" mentah dari Sheets ke DB, padahal sistem standar pakai "OK"
2. **`verify_all_urls_today` delta hanya cek `== "OK"`** — tidak mengenali "SUCCESS" sebagai status OK lama, sehingga tidak mengurangi `ok_delta`
3. **Timezone UTC vs WIB** — admin verify dan scheduler pakai UTC, sehingga antara 00:00–07:00 WIB, data di-query dari tanggal salah

### Decisions
1. **Timezone default: WIB (Asia/Jakarta)** — Semua pengguna di Indonesia, Google Sheets timezone WIB, dan staff handlers sudah WIB. Tidak ada alasan menggunakan UTC.
2. **Status default: `OK`** — Sesuai enum `VerifStatus.OK` dan CHANGELOG. Helper `_normalize_status()` mengkonversi "SUCCESS" → "OK" sebelum disimpan ke DB, memutus siklus infinite loop.
3. **Centralized helpers**: `_is_ok_status()` menjadi single point untuk pengecekan status OK agar delta counting benar — mengenali "SUCCESS" dan "OK" sebagai equivalen.

### Affected Files
- `bot/services/sheet_parser.py` — Normalisasi status + fix delta counting (memutus siklus)
- `bot/handlers/admin.py` — 4 fungsi UTC → WIB
- `bot/scheduler.py` — auto_verify UTC → WIB
- `BOTS_STRIPE_VERIF_DASHBOARD/js/dashboard.js` — `todayStr()` dan analytics UTC → WIB
- `scripts/restore_sheets_assignment.py`, `scripts/compare_db_sheets.py` — UTC → WIB

## [2026-06-13] - Refactor Staff Bulk Verification Screen

### Context
1. Staff members clicking "⚡ Verif Semua PENDING" were immediately blocked with a raw "Kuota Staff Terpenuhi" warning if they had reached their daily quota, which was frustrating and uninformative.
2. We want to motivate staff to perform checks mindfully (work psychology) rather than just clicking bulk verification mindlessly.
3. During verification execution, there was no indicator showing how many links were being validated out of the total, leading to a lack of feedback.

### Decisions
1. **Interactive Status Dashboard instead of Raw Quota warnings**:
   - *Decision*: Modify `cb_url_verify_all` to show an interactive dashboard containing Link Aktif (OK status), Link Semua (total today), and user contributions, removing raw warning messages.
   - *Rationale*: Hiding raw warning blocks and displaying data statistics keeps staff informed of the exact task status while respecting user directives.
2. **Work Psychology Confirmation & Responsibility Reminder**:
   - *Decision*: Introduce a confirmation step ("✅ Ya, Jalankan Verifikasi") featuring a staff responsibility disclaimer rather than immediately verifying everything upon clicking.
   - *Rationale*: Promotes conscious execution and reinforces staff accountability for verified data.
3. **Live Progress Animating Counters**:
   - *Decision*: Implement throttled live message editing (`progress_cb`) displaying the current verification progress `(N/Total)` alongside cycling emojis, with updates limited to every 1.5 seconds.
   - *Rationale*: Prevents Telegram API rate limits while keeping staff engaged with a dynamic progress bar during bulk operations.
4. **Persistent Bulk Verification Visibility**:
   - *Decision*: Keep the `⚡ Verif Semua PENDING` button visible on the URL list menu regardless of quota state.
   - *Rationale*: Allows staff members to access the status dashboard at any time to review today's counts.

## [2026-06-12] - Sync Sheets to DB & Verify All Staff Metric Protections

### Context
1. Admin memicu "Verify All" dan hal ini menimpa kolom `verified_by` di DB dengan ID Admin untuk semua URL harian, yang menyebabkan data kontribusi staf di dashboard hilang.
2. Penugasan di Google Sheets (Kolom F / Assigned By) tidak boleh tertimpa saat penulisan status kembali ke Sheets.
3. Dibutuhkan cara menarik kembali status final dan nama verifikator dari Google Sheets ke DB PostgreSQL demi pemulihan atau sinkronisasi balik (reverse sync).

### Decisions
1. **Proteksi ID Staf di Database**:
   - *Decision*: Mengubah logika update `verified_by` di DB pada fungsi `verify_all_urls_today` agar mempertahankan ID staf asli jika sudah terisi.
   - *Rationale*: Mencegah admin menimpa status verifikator asli dari staf dan menjaga keakuratan metrik progress staf di dashboard.
2. **Proteksi Kolom F Google Sheets**:
   - *Decision*: Menjaga logika penulisan status di `doPost` Apps Script agar tidak memodifikasi `COL_ASSIGN_BY` (Kolom F) saat status adalah status verifikasi final.
   - *Rationale*: Menghindari hilangnya data assignment staff di spreadsheet seperti yang diminta oleh user.
3. **Penyediaan Tombol Sinkronisasi Balik**:
   - *Decision*: Menghapus tombol legacy `Push Assign → Sheet` (yang tidak lagi dibutuhkan) dan menggantinya dengan tombol `Sync Sheets → DB` (`sync_status_to_db`).
   - *Rationale*: Mengarahkan alur kerja admin agar dapat memperbarui status dari Google Sheets ke database lokal secara efisien.
4. **Parameter all/sync di doGet Apps Script**:
   - *Decision*: Menambahkan parameter query `all=1` pada doGet Apps Script agar mengembalikan semua baris (termasuk yang berstatus final) dan mengembalikan kolom verifikator/assignee.
   - *Rationale*: Tanpa parameter ini, Apps Script secara default mengabaikan baris yang sudah final sehingga bot tidak bisa mensinkronisasi baris yang sudah selesai dari Sheets.

## [2026-06-12] - Leonardo API Key Credits Verification, Progress Tracking, and Verify All Today

### Context
1. User meminta bot melakukan pengecekan kredit/token API Key Leonardo.ai dengan menjumlahkan `subscriptionTokens` + `paidTokens` + `apiPaidTokens` mengacu pada implementasi `Generative-Leo`.
2. Jika Stripe URL error (tanda sudah dibayar/expired) ATAU kredit API Key > 0, status akhir verifikasi adalah sukses (OK). Selain itu, status akhir verifikasi dianggap gagal (FAIL).
3. Dibutuhkan proxy dinamis yang bisa dirotasi per request untuk menghindari ban/rate limit saat memanggil endpoint Leonardo.ai.
4. Diperlukan tampilan visual kemajuan (progress tracking) saat melakukan sinkronisasi maupun verifikasi massal agar user mengetahui proses sedang berjalan.
5. Admin membutuhkan tombol verifikasi massal langsung pada seluruh link hari ini dan hasilnya terupdate di Google Sheets.

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
4. **Pembatasan Kecepatan Edit Pesan Progress (Throttling)**:
   - *Decision*: Menerapkan progress callback dengan pembatasan waktu edit pesan minimal 1.5 detik sekali.
   - *Rationale*: Menghindari bot terkena pemblokiran laju kirim pesan (rate limit) Telegram API saat memproses verifikasi massal yang berjalan cepat dan konkuren.
5. **Pemisahan Alur Verifikasi Massal**:
   - *Decision*: Membuat fungsi core `verify_all_urls_today` di `sheet_parser.py` dan mendaftarkan tombol **`⚡ Verif Semua`** serta command `/verify_all` di `admin.py`.
   - *Rationale*: Memberikan keleluasaan bagi admin untuk memicu pengecekan & penulisan status final ke Google Sheets kapan saja tanpa menunggu scheduler berkala.

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




