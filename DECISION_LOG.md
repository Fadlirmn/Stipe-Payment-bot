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
5. **Leonardo API Key Checker Integration & Sheet Sync**:
   - *Decision*: Adopt the checking method from `Leo-bot-new/api-checker` by calling the Leonardo `/me` endpoint to retrieve active token counts (free + paid + api paid) and renewal date. When verified, call Apps Script `copyActiveKey` payload via POST request asynchronously.
   - *Rationale*: Automates key population into the "Active Keys" sheet immediately after successful payment verification.
6. **Exemption of Admins & Devs from Staff Quotas**:
   - *Decision*: Bypass the `quota_exceeded` checks when rendering the verification button for users with admin or dev roles.
   - *Rationale*: Admins and developers must be able to perform manual verification or overrides even if the regular staff quota limit has been reached.

