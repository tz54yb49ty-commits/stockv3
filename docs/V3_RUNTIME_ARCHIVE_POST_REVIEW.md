# V3 Runtime Archive Post Review

Result: `POST_REVIEW_PASS`

Trade date: `20260612`
Manifest: `/Volumes/MacRaid/stock_db_archive/v3_runtime/trade_date=20260612/manifests/archive_manifest.json`
Rows: `2444131`
Files: `49`
Row count match: `True`
Live count mismatches: `0`
UI: `/n6/archive-status`

## Rows By Layer
- n3: `1985969` rows / `22` files
- n4: `371301` rows / `12` files
- n5: `86861` rows / `11` files
- n6: `0` rows / `4` files

## Cleanup
- cleanup executed: `False`
- cleanup eligible: `False`
- cleanup guard: `sql/V3_runtime_archive_manual_cleanup_guard.sql`

## Forbidden Scope
- database_written: `False`
- local_runtime_cleanup_executed: `False`
- outbox_inbox_checkpoint_consumed_or_updated: `False`
- worker_or_scheduler_started: `False`
- n6_voice_mobile_sim_position_trade_touched: `False`
- old_system_touched: `False`
- rollback_executed: `False`
