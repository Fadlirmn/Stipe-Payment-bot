# Decision Log

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




