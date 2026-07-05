# N3 20260612 B1 Fact-Only Source Time Semantics Policy And Failed Run Cleanup

- result: `REPAIR_PASS`
- layer_role: `N3_market_data`
- cleanup_sql: `sql/N3_20260612_B1_fact_only_failed_runs_cleanup.sql`

## Source-Time Policy

- untrusted period label handling: `NORMALIZE_TO_OBSERVED_AT`
- event_time_policy: `observed_at_for_untrusted_period_label`
- quality-visible status: `source_time_label_normalized`
- writes_outbox: `false`

## Live Run Registry
- `realtime_daily_snapshot_20260612_until_1005__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`: status=`failed`, snapshots={'stock_realtime_daily_snapshot': 1872, 'index_realtime_daily_snapshot': 2, 'board_realtime_daily_snapshot': 0}, quality=219, outbox/inbox/checkpoint=0/0/0
- `realtime_daily_snapshot_20260612_until_1008__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`: status=`failed`, snapshots={'stock_realtime_daily_snapshot': 1872, 'index_realtime_daily_snapshot': 2, 'board_realtime_daily_snapshot': 0}, quality=219, outbox/inbox/checkpoint=0/0/0
- `realtime_daily_snapshot_20260612_until_1011__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`: status=`failed`, snapshots={'stock_realtime_daily_snapshot': 1872, 'index_realtime_daily_snapshot': 2, 'board_realtime_daily_snapshot': 0}, quality=219, outbox/inbox/checkpoint=0/0/0
- `realtime_daily_snapshot_20260612_until_1014__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`: status=`running`, snapshots={'stock_realtime_daily_snapshot': 1281, 'index_realtime_daily_snapshot': 2, 'board_realtime_daily_snapshot': 0}, quality=208, outbox/inbox/checkpoint=0/0/0

## Cleanup Scope

- delete only: `stock/index/board_realtime_daily_snapshot`, `common_market_data_quality_item`, `common_market_data_run` for the four target run_ids
- hard-fail before first `DELETE`: `true`
- event/downstream refs must be zero before cleanup
- no `DROP` / `TRUNCATE` / `CASCADE`

## Forbidden Scope

No scheduler start/modify, no wrapper/B1/C1/B2/N4/N5 execute, no N6, no outbox/inbox/checkpoint consumption/update, no worker, no voice/mobile/sim/trade, no old system touch.

## Validation

- targeted intraday child + cleanup tests: `PASS`
- targeted realtime snapshot tests: `PASS`
- JSON parse: `PASS`
- compileall: `PASS`
- schema column check: `PASS`
- cleanup static check: `PASS`
- git diff --check: `PASS`
