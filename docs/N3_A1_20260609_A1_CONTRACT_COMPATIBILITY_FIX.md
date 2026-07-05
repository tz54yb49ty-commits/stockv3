# N3-A1 20260609 A1 Contract Compatibility Fix

## Result

- result: `FIX_PASS`
- layer_role: `N3_market_data`
- source_subscription_run_id: `market_data_subscription_20260609_condition_layer_20260608_source_20260608_for_20260609_v1`
- preload_run_id: `previous_day_minute_preload_20260608_for_20260609__market_data_subscription_20260609_condition_layer_20260608_source_20260608_for_20260609_v1`
- previous_day_minute_date: `20260608`
- data_trade_date: `20260608`
- required_data_kind: `previous_day_minute_bar_1m`
- historical_preload: `true`

## Root Cause

Stage 2 was blocked before DB write because the previous gate-level contract used a non-runner stage value. The existing A1 execute runner requires `stage=N3-A1-preflight`.

## Fix

- Regenerated A0 dry-run from the persisted Stage 1 subscription run.
- Regenerated A1 execute contract and preflight through the canonical A1 contract planner.
- Added explicit direct-alias fields to the contract generator:
  - `source_subscription_run_id`
  - `data_trade_date`
  - `required_data_kind`
  - `historical_preload`
- Propagated those fields into the execute preflight artifact.

## Proof

- contract stage: `N3-A1-preflight`
- preflight result: `PREFLIGHT_PASS`
- P0/P1/P2: `0/0/0`
- expected objects stock/index/board/total: `289/51/11/351`
- expected minute rows stock/index/board/total: `69360/12240/2640/84240`
- A1 target baseline total: `0`
- Stage 1 subscription run status: `passed`

## Rollback Scope Update

`N3_A1_20260609_ROLLBACK_SCOPE_REPAIR_GATE` updated `sql/N3_A1_previous_day_minute_20260609_rollback.sql` after this compatibility fix. The rollback scope now covers both the already executed Stage 1 subscription control rows and the future Stage 2 A1 preload rows.

## Boundary

This gate did not execute Stage 2, did not write A1 minute/status/quality/run rows, did not rerun Stage 1, did not touch outbox/inbox/checkpoint, and did not enter N3-B/C/B2/N4/N5/N6.
