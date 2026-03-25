# CRON.md – Scheduled Tasks

This file defines when the assistant should run periodic checks.

## Critical Change Check

**Action:**
- Read the latest available day's data from the Google Sheet.
- Evaluate against thresholds in `CONFIG.md`:
  - Revenue drop > `revenue_drop_pct` vs average of last 7 days (excluding today)
  - Conversion rate < `conversion_threshold`
  - Upsell drop > `upsell_drop_pct` vs average of last 5 days
  - Plan deviation > `plan_deviation_pct` (if today's plan exists)
- If any critical change is detected, send a message with the details.
- If no critical changes, do nothing.

If you see any other critical changes, act proactively and notify a user
