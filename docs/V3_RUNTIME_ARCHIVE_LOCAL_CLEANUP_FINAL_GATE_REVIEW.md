# V3 Runtime Archive Local Cleanup Final Gate Review

Result: `BLOCKED`

Trade date: `20260612`

This gate reviewed whether the verified 20260612 V3 runtime archive can proceed to local hot-store cleanup. Cleanup was not executed.

## Archive Verified Proof

- Manifest: `/Volumes/MacRaid/stock_db_archive/v3_runtime/trade_date=20260612/manifests/archive_manifest.json`
- Archive report: `/Volumes/MacRaid/stock_db_archive/v3_runtime/trade_date=20260612/reports/archive_report.json`
- Manifest result: `ARCHIVED_VERIFIED`
- Files: `49`
- Rows: `2444131`
- Row count match: `true`
- Live manifest-scope mismatches: `0`
- Live manifest-scope rows: `2444131`

## UI Proof

`/n6/archive-status` is aligned with the MacRaid manifest:

- Archive State: `ARCHIVED_VERIFIED`
- Execute Result: `EXECUTE_PASS`
- Files: `49`
- Rows: `2444131`
- row_count_match: `true`
- Cleanup: `waiting`
- Cleanup buttons/forms: absent

## Cleanup SQL Proof

Current cleanup guard:

`sql/V3_runtime_archive_manual_cleanup_guard.sql`

Proof:

- hard-fail exists before first `DELETE`
- requires `ashare_v3.allow_v3_runtime_archive_manual_cleanup=true`
- requires `ashare_v3.archive_manifest_verified=true`
- current executable delete scope is still `WHERE false`

This SQL is safe as a guard, but it is not yet a real scoped hot-store cleanup implementation.

## Live DB Guard Proof

Clean guards:

- delivering outbox refs: `0`
- event delivery attempts: `0`
- N6 user projection refs: `0`
- N6 user signal projection/card/notification refs: `0/0/0`
- position refs: `0/0`
- business writer process count: `0`
- trading scheduler labels:
  - `com.ashare-v3.v3-realtime-engine`: `not_loaded`
  - `com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll`: `not_loaded`
  - `com.ashare-v3.n4.bounded-polling`: `not_loaded`

Observed stale archived runtime row:

- `common_market_data_run.status=running`
- run_id: `realtime_daily_snapshot_20260612_standard_outbox_until_1314__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`
- started_at: `2026-06-12T13:18:37.012397+08:00`
- `worker_started=false`
- `market_data_pulled=false`
- `market_data_fact_written=false`
- no matching business writer process observed

This row is classified as stale archived runtime state, not an active process, but the cleanup implementation must still handle it explicitly.

## Blocking Findings

P0: `non_archived_previous_day_minute_preload_status_refs`

Three N3 previous-day preload status tables reference 20260612 `common_market_data_run` rows but are not present in the 49-file MacRaid manifest:

- `stock_previous_day_minute_preload_status`: `245`
- `index_previous_day_minute_preload_status`: `33`
- `board_previous_day_minute_preload_status`: `19`

Deleting parent `common_market_data_run` rows would cascade-delete these unarchived status rows. Local cleanup must not proceed until these rows are archived or explicitly retained by reviewed policy.

P0: `cleanup_sql_guard_only_noop`

The current manual cleanup SQL is guard-only and uses `DELETE ... WHERE false`. It cannot be used to complete actual local hot-store cleanup.

## Forbidden Scope Proof

- cleanup executed: `false`
- database written: `false`
- rollback executed: `false`
- archive rerun: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- N3/N4/N5/N6 business runner executed: `false`
- worker/scheduler started: `false`
- voice/mobile/sim/position/order/real trade touched: `false`
- old system touched: `false`

## Decision

Local cleanup execute is not allowed.

Next recommended gate:

`V3_RUNTIME_ARCHIVE_SUPPLEMENTAL_PREVIOUS_DAY_PRELOAD_STATUS_ARCHIVE_CONTRACT_PREFLIGHT_GATE`

## Next Prompt

```text
layer_role=N1_ingestion。

进入 V3_RUNTIME_ARCHIVE_SUPPLEMENTAL_PREVIOUS_DAY_PRELOAD_STATUS_ARCHIVE_CONTRACT_PREFLIGHT_GATE。

目标：只读制定 20260612 runtime archive supplemental contract/preflight，补齐当前 manifest 缺失但会被 common_market_data_run cleanup 级联影响的 N3 previous-day preload status 三张表：stock_previous_day_minute_preload_status、index_previous_day_minute_preload_status、board_previous_day_minute_preload_status。不得执行归档、不得清理本地热库、不得写 DB、不得消费/update outbox/inbox/checkpoint、不得进入 N3/N4/N5/N6 runner、不得触碰 voice/mobile/sim/position/order/real trade。输出 CONTRACT_PREFLIGHT_PASS / BLOCKED、supplemental file plan、row-count proof、manifest update policy、cleanup readiness impact、next prompt。
```
