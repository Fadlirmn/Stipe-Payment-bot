# Changelog

All notable changes to this project will be documented in this file.

## [2026-06-12] — Reconcile & Re-verify Failed URLs, Menu Cleanup, and Bugfixes

### Added
- `[Added]` Periodic scheduler job `job_auto_verify_failed` in `scheduler.py` that runs every 15 minutes to reconcile failed database URLs against Google Sheets and perform re-verifications.
- `[Added]` Core function `reconcile_and_verify_failed_urls` in `sheet_parser.py` shared by both the admin command and background scheduler task.

### Fixed
- `[Fixed]` Solved `Button_data_invalid` callback query crash in Telegram bot by shortening retry button `callback_data` to remain under the 64-byte Telegram limit.
- `[Fixed]` Resolved `NameError: name 'logger' is not defined` inside `bot/handlers/admin.py` by importing `logger` from `loguru`.

### Removed
- `[Removed]` Backup and restore SQLite / PostgreSQL manual buttons and their descriptions from `cb_menu_devtools` keyboard inside `bot/handlers/admin.py` to keep the UI focused on verification.

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





