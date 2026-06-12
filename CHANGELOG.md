# Changelog

All notable changes to this project will be documented in this file.

## [2026-06-12]

### Fixed
- `[Fixed]` Synchronized verification link assignments when `quota_per_staff` changes. If quota increases, it automatically assigns new pending links to staff. If quota decreases, it retains already assigned links.
- `[Fixed]` Stripe verifier now checks for payment completion (HTML text matching and success redirects) instead of just checking if the page is reachable.

### Added
- `[Added]` Standalone CLI verifier script `scripts/verify_link.py` for manual checkout checks.
- `[Added]` Reusable global connection pooling client `_client` in `url_verifier.py` to optimize concurrent verifications.
- `[Added]` `copy_active_key_to_sheet` in `services/sheet_parser.py` to support copying active Leonardo API keys to Sheet 2 (Active Keys) using POST requests.
- `[Added]` `Check API Keys` button in Dev Tools menu (and command `/check_api_keys`) to manually check all API Keys and sync active/expired ones to Sheet 2.

### Changed
- `[Changed]` Excluded admin and dev roles from quota limit enforcement so they can always view and verify links.
- `[Changed]` Excluded copying of active keys to Sheet 2 during Stripe URL check flow; copying is now restricted exclusively to the manual `Check API Keys` action.
- `[Changed]` `check_leonardo_api_key` in `services/url_verifier.py` to check token details without writing directly to Sheet 2.


