# N3 20260612 B1 Fact-Only Interrupted Run 1422 Cleanup Execute Report

Result: `CLEANUP_PASS`

Target run:

`realtime_daily_snapshot_20260612_until_1422__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`

## Before

- `common_market_data_run`: `1`
- `common_market_data_quality_item`: `0`
- stock/index/board snapshot: `0/37/127`
- outbox/inbox refs: `0/0`
- B2 projection refs: `0`

## After

- `common_market_data_run`: `0`
- `common_market_data_quality_item`: `0`
- stock/index/board snapshot: `0/0/0`
- outbox/inbox refs: `0/0`
- B2 projection refs: `0`

## Safety

Cleanup SQL: `sql/N3_20260612_B1_fact_only_interrupted_run_1422_cleanup.sql`

- required explicit setting: `ashare_v3.allow_n3_b1_20260612_interrupted_cleanup=true`
- hard-fail before first `DELETE`
- scope limited to the single interrupted B1 fact-only run
- no `DROP`, `TRUNCATE`, or `CASCADE`

No scheduler start, no manual wrapper/N4/N5 execution, no rollback, no outbox/inbox/checkpoint consumption or update, no N6, no voice/mobile/sim/trade.
