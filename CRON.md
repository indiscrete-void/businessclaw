# CRON.md – Scheduled Tasks

This file defines when the assistant should run periodic checks.

## Critical Change Check

Run this task **every weekday at 09:00** (or after business hours to catch previous day's data). Adjust as needed.

**Schedule:** `0 9 * * 1-5` (Monday through Friday, 9:00 AM)

**Action:**
- Read the latest available day's data from the Google Sheet.
- Evaluate against thresholds in `CONFIG.md`:
  - Revenue drop > `revenue_drop_pct` vs average of last 7 days (excluding today)
  - Conversion rate < `conversion_threshold`
  - Upsell drop > `upsell_drop_pct` vs average of last 5 days
  - Plan deviation > `plan_deviation_pct` (if today's plan exists)
- If any critical change is detected, send a Telegram message with the details.
- If no critical changes, do nothing.

**Note:** The assistant will be invoked with a context that includes this task name. You can identify it by looking for a `task` field in the incoming request, or by the fact that no user query is present. Follow the instructions above without waiting for user input.

## Adding More Tasks

To add a new scheduled task, add a new section with a schedule and description. The assistant will need to handle it accordingly. Keep the format simple.
