# V3 Runtime Archive Status 20260612 - Hot Store Restored

- result: `RESTORE_PASS`
- trade_date: `20260612`
- root cause: `20260612 was cleaned despite today_plus_recent_5_trade_days retention policy`
- manifest: `/Volumes/MacRaid/stock_db_archive/v3_runtime/trade_date=20260612/manifests/archive_manifest.json`
- manifest rows/files: `52` / `2444428`
- N3 outbox rows: `22902`
- N4 outbox rows: `103862`
- N5 outbox rows: `27469`
- N4 state/match: `148131` / `82522`
- N5 action_event: `27469`
- delivering outbox rows: `0`

## Retention Guard

`sql/V3_runtime_archive_manual_cleanup_guard.sql` now blocks `today_plus_recent_5_trade_days` cleanup unless `ashare_v3.allow_v3_runtime_archive_cleanup_recent_trade_date=true` is set by a separate reviewed final gate.

## Boundary

No N3/N4/N5/N6 business runner was executed. No worker/scheduler was started. No outbox/inbox/checkpoint was consumed or updated. Old system was not touched.
