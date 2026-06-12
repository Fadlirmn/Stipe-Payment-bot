# Changelog

All notable changes to this project will be documented in this file.

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





