# Decision Log

## [2026-06-12] - Task Quota Sync Implementation

### Context
When the task quota is changed, the pre-assigned pending links for users today become out of sync, locking them for users who can no longer verify them.

### Decisions
1. **Unassign Excess Links**:
   - *Decision*: Reset `verified_by = NULL` and `assigned_at = NULL` in the database.
   - *Rationale*: Frees up links to be claimed by other active staff members.
2. **Google Sheets Status Reset**:
   - *Decision*: Call `update_sheet_status` with `status = ""` and `staff_info = ""` in a background non-blocking coroutine.
   - *Rationale*: Resets the status column on Google Sheets, allowing the Apps Script `doGet` function to expose those links to the bot again.
