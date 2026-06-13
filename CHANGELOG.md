# Changelog

All notable changes to this project will be documented in this file.

## [2026-06-13] — Fix Timezone & Status Inconsistency (Dashboard Ngaco)

### Fixed
- `[Fixed]` **Timezone Inconsistency**: Admin handlers (`cmd_verify_failed`, `cmd_verify_all`, `cmd_sync_status_to_db`, `cmd_push_verified_status`) dan scheduler `job_auto_verify_failed` menggunakan UTC, sementara staff handlers dan Google Sheets menggunakan WIB. Antara 00:00–07:00 WIB, tanggal "hari ini" berbeda antara UTC dan WIB sehingga data terpecah. Sekarang seluruh sistem menggunakan **WIB (Asia/Jakarta)**.
- `[Fixed]` **Dashboard `todayStr()` UTC Bug**: Frontend dashboard menggunakan `.toISOString()` yang selalu mengembalikan UTC. Date picker default dan analytics chart sekarang menggunakan timezone WIB.
- `[Fixed]` **Status `SUCCESS` vs `OK` Double Counting**: `sync_status_from_sheets_to_db` menyimpan status mentah dari Sheets tanpa normalisasi. Jika Sheets berisi "SUCCESS", DB menyimpan "SUCCESS" sementara dashboard hanya query `status == 'OK'`. Sekarang status dinormalisasi via `_normalize_status()` (SUCCESS → OK).
- `[Fixed]` **Progress Delta Double Counting**: `verify_all_urls_today` hanya mengecek `old_status == "OK"` tanpa meng-handle "SUCCESS", menyebabkan `ok_delta` tidak dikurangi saat re-verifikasi URL yang sebelumnya "SUCCESS". Sekarang menggunakan `_is_ok_status()` helper.
- `[Fixed]` **Status Reset During Sheets->DB Sync**: `sync_status_from_sheets_to_db` did not check if the status in the DB was already final (e.g. `OK`, `FAILED`) before updating it with status from Google Sheets. This could cause verified URLs to be reset to "PENDING" or "ASSIGNED" when syncing. Added checks to prevent overwriting a final DB status with a non-final status from Sheets.
- `[Fixed]` **Daily Report & EOD Summary Metrics**: The daily report (`cmd_report`) and scheduler EOD summary (`job_eod_summary`) fetched counts from the corrupted `task_progress` table, showing incorrect (sometimes negative) verified counts per staff member. They now query `sheet_urls` directly for the current date, guaranteeing 100% accurate metrics matching the dashboard.
- `[Fixed]` **Link Claim `assigned_to` Population**: Added database updates to properly populate and preserve the `assigned_to` field during `get_or_claim_next_url` operations for both PostgreSQL and SQLite. This ensures URLs claimed by staff through "Ambil Link" are properly attributed to them in the dashboard stats.

### Changed
- `[Changed]` Menambahkan helper functions `_normalize_status()` dan `_is_ok_status()` di `sheet_parser.py` sebagai single source of truth untuk normalisasi dan pengecekan status OK.
- `[Changed]` Rename parameter `target_date_utc` → `target_date_str` di fungsi `reconcile_and_verify_failed_urls`, `verify_all_urls_today`, dan `sync_status_from_sheets_to_db` untuk kejelasan.
- `[Changed]` Scripts `compare_db_sheets.py` dan `restore_sheets_assignment.py` diupdate dari UTC ke WIB.
- `[Changed]` Updated daily report, EOD summary scheduler, and dashboard stats (Staff Monitor & Rate per User) to group strictly by `assigned_to` instead of `verified_by`, normalized metrics to Submitted, OK, and Gagal (any non-OK status), and added OK/task completion percentage formatting.

## [2026-06-13] — Refactor Staff Bulk Verification Screen

### Added
- `[Added]` Fungsi callback `cb_url_verify_all_confirm` di `verif.py` untuk menjalankan verifikasi massal dengan animasi kemajuan (N/Total) dan throttling update setiap 1.5 detik.

### Changed
- `[Changed]` Mengubah `cb_url_verify_all` di `verif.py` agar menampilkan dashboard status interaktif (Link Aktif, Link Semua, dan Progress Staff) dengan pesan tanggung jawab psikologis, alih-alih menampilkan warning quota "memenuhi kuota" langsung.
- `[Changed]` Memodifikasi `_show_url_list` di `verif.py` agar tombol "⚡ Verif Semua PENDING" selalu ditampilkan walaupun kuota staf sudah penuh, sehingga staf tetap dapat melihat panel status dashboard verifikasi massal.

## [2026-06-12] — Sync Sheets to DB & Verify All Staff Metric Protections

### Added
- `[Added]` Fungsi `sync_status_from_sheets_to_db` di `sheet_parser.py` untuk mensinkronisasi status verifikasi dan verifikator dari Google Sheets ke DB.
- `[Added]` Fungsi `resolve_user_id_by_string` di `sheet_parser.py` untuk resolusi user ID dari username/fullname.
- `[Added]` Tombol baru **📥 Sync Sheets → DB (Status)** dan callback handler `sync_status_to_db` pada devtools menu.

### Fixed
- `[Fixed]` Memperbaiki hilangnya data kontribusi staf di DB/dashboard saat admin memicu "Verify All". Sekarang `verified_by` yang berisi ID staf akan tetap dipertahankan dan kemajuannya diupdate ke `task_progress` milik staf.

### Changed
- `[Changed]` Memodifikasi Apps Script `doGet` dan `fetch_today_urls` agar mendukung parameter query `all=1` untuk mendapatkan seluruh baris (termasuk yang berstatus final) dan mengembalikan data verifikator/assignee.
- `[Changed]` Mengganti tombol `📤 Push Assign → Sheet` dengan tombol sinkronisasi status dari Google Sheets ke DB.

## [2026-06-12] — Leonardo API Key Credits Verification, Progress Tracking, and Verify All Today

### Added
- `[Added]` Fungsi `check_leonardo_api_key_credits` di `url_verifier.py` yang menjumlahkan `subscriptionTokens` + `paidTokens` + `apiPaidTokens` untuk sisa kuota numerik API Key Leonardo.ai berdasarkan referensi `Generative-Leo`.
- `[Added]` Fungsi async `get_rotated_proxy_url` di `url_verifier.py` untuk mendukung perutean dynamic proxy (Croxy API) atau static session-rotated proxy.
- `[Added]` Konfigurasi `PROXY_URL` dan `RESIDENTIAL_PROXY_URL` pada file `.env` dan `config.py` proyek.
- `[Added]` Fungsi terpadu `verify_stripe_and_credits` di `url_verifier.py`.
- `[Added]` Fitur progress tracking visual (e.g. `(5/20)`) untuk proses sync sheet (`action == "sync"`) dan verifikasi massal.
- `[Added]` Fungsi `verify_all_urls_today` di `sheet_parser.py` dan tombol inline **`⚡ Verif Semua`** serta command `/verify_all` di `admin.py` untuk memicu verifikasi massal semua URL hari ini dan memperbarui statusnya langsung ke database & Google Sheets.

### Changed
- `[Changed]` Mengubah logika verifikasi di `verif.py` dan `sheet_parser.py` menjadi: Jika Stripe URL error/mati ATAU sisa kredit Leonardo API Key > 0, maka hasil verifikasi adalah `OK` (sukses). Selain kondisi itu, maka `HTTP_ERR` (gagal).
- `[Changed]` `check_leonardo_api_key` kini menjadi legacy wrapper yang memanggil fungsi baru `check_leonardo_api_key_credits`.
- `[Changed]` Memodifikasi `reconcile_and_verify_failed_urls` dan `cmd_verify_failed` agar mendukung throttled `progress_callback` untuk mencegah limitasi laju Telegram (rate limit).

## [2026-06-12] — Reconcile & Re-verify Failed URLs, Menu Cleanup, and Bugfixes

### Added
- `[Added]` Periodic scheduler job `job_auto_verify_failed` in `scheduler.py` that runs every 15 minutes to reconcile failed database URLs against Google Sheets and perform re-verifications.
- `[Added]` Core function `reconcile_and_verify_failed_urls` in `sheet_parser.py` shared by both the admin command and background scheduler task.

### Fixed
- `[Fixed]` Solved `Button_data_invalid` callback query crash in Telegram bot by shortening retry button `callback_data` to remain under the 64-byte Telegram limit.
- `[Fixed]` Resolved `NameError: name 'logger' is not defined` inside `bot/handlers/admin.py` by importing `logger` from `loguru`.
- `[Fixed]` Aborted the reconciliation process immediately if Google Sheets fetch fails, preventing incorrect status updates to `OK` due to network timeouts.
- `[Fixed]` Improved `check_leonardo_api_key` in `url_verifier.py` to parse JSON and check both `apiCreditBalance` and `subscriptionTokens`; the key is marked as `EXPIRED` (Stripe unpaid) if both are <= 0.

### Changed
- `[Changed]` Increased default HTTP timeout to 30.0 seconds to accommodate slow responses from Google Apps Script Web App.

### Removed
- `[Removed]` Backup and restore SQLite / PostgreSQL manual buttons and their descriptions from `cb_menu_devtools` keyboard inside `bot/handlers/admin.py` to keep the UI focused on verification.
- `[Removed]` **Push Status → Sheet** button and its corresponding description from `cb_menu_devtools` inside `bot/handlers/admin.py`.

---

## [2026-06-12] — Fix ensure_quota_synced TypeError

### Fixed
- `[Fixed]` `postgres_ensure_quota_synced` dan `sqlite_ensure_quota_synced` mengembalikan `int` padahal caller (`_show_url_list`) mengiterasinya sebagai `list[dict]`. Menyebabkan crash: `TypeError: 'int' object is not iterable` saat staff membuka Daftar Link di bot Telegram.
- `[Fixed]` Query di `ensure_quota_synced` diubah dari `SELECT id` ke `SELECT *` agar URL objects lengkap dikembalikan untuk digunakan oleh Sheet sync.

---

## [2026-06-12] — Menu Cleanup

### Removed
- `[Removed]` Tombol 🔔 Set Reminder dari menu admin/dev — fitur belum diimplementasi (placeholder only).
- `[Removed]` Tombol 📊 Dashboard dari Dev Tools panel — duplikat dengan menu utama admin/dev.
- `[Removed]` Handler `cb_menu_reminder` dan registrasi callback `menu:reminder` dari `admin.py`.

### Rationale
- Pembersihan menu agar fokus pada fitur inti: **cek link** (verifikasi URL Stripe) dan **sync ke Google Sheets**.
- Menu yang dipertahankan: Task, Progress, Verif URL, History, Config Task, Kelola User, Report, Dashboard (menu utama), Dev Tools, Bantuan.

---

## [2026-06-12]

### Fixed
- `[Fixed]` Synchronized verification link assignments when `quota_per_staff` changes. If quota increases, it automatically assigns new pending links to staff. If quota decreases, it retains already assigned links.
- `[Fixed]` Stripe verifier now checks for payment completion (HTML text matching and success redirects) instead of just checking if the page is reachable.
- `[Fixed]` Synchronized task listing fields by mapping `task_id` to `id` in `postgres_list_tasks`, `sqlite_list_tasks`, and `sqlite_get_task` to prevent `KeyError: 'id'` in admin and synchronization handlers.

### Added
- `[Added]` Standalone CLI verifier script `scripts/verify_link.py` for manual checkout checks.
- `[Added]` Reusable global connection pooling client `_client` in `url_verifier.py` to optimize concurrent verifications.

### Changed
- `[Changed]` Excluded admin and dev roles from quota limit enforcement so they can always view and verify links.
- `[Changed]` `check_leonardo_api_key` in `services/url_verifier.py` to check token details without writing directly to Sheet 2.
- `[Changed]` Updated the message text styling and layout of `cb_menu_devtools` in `bot/handlers/admin.py` to display descriptions for User Management, Task & Synchronization, and Verification & Database tools.
- `[Changed]` Configured connection pool limits on the global AsyncClient to handle high concurrent multi-user load.
- `[Changed]` Enforced concurrency limits (max 5 parallel requests) in bulk verification to prevent Leonardo/Stripe API rate limit exhaustion.
- `[Changed]` Integrated Leonardo API key checking in admin re-verification (`cmd_verify_failed`) to ensure consistent verification logic.





