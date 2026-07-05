# N3 20260612 B1 Dynamic Child Artifact Subscription Count Repair

- gate: `N3_20260612_B1_DYNAMIC_CHILD_ARTIFACT_SUBSCRIPTION_COUNT_REPAIR_GATE`
- layer_role: `N3_market_data`
- result: `REPAIR_PASS`
- source subscription run: `market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`

## Root Cause

The dynamic intraday child artifact generator only loaded counts from fixed dry-run/report artifact names. When those artifacts were absent for 20260612, it fell back to schema-only zero counts and generated B1 contract/readiness with stock/index/board `0/0/0`.

## Repair

- Added explicit `subscription_summary` injection to `IntradayChildArtifactRequest`.
- Added wrapper read-only live subscription count loading from `common_market_data_subscription`.
- Count query uses `default_transaction_read_only=on`.
- B1 contract/readiness now use live `realtime_daily_snapshot` counts.
- C1/B2 dynamic artifacts also receive live `minute_bar_1m` / snapshot counts.

## Live Count Proof

```text
realtime_daily_snapshot stock/index/board = 1872/83/127
minute_bar_1m stock/index/board = 245/33/19
```

## Refreshed Artifact Scope

Refreshed existing 20260612 dynamic bundles:

```text
auction HHMM = 0920-0931
closed-minute HHMM = 0931-0936
B1 expected_asset_counts = stock/index/board 1872/83/127
B1 expected_row_count = 2082
```

## Boundary

```text
scheduler_installed_or_modified=false
wrapper_executed=false
B1_C1_B2_execute=false
N4_N5_N6_execute=false
database_written=false
rollback_executed=false
outbox_inbox_checkpoint_consumed_or_updated=false
worker_started=false
old_system_touched=false
delivery_push_voice_mobile=false
proposal_order_trade_sim_position_pnl_real_trade=false
```

## Validation

```text
targeted_intraday_tests=PASS
json_parse=PASS
compileall=PASS
git_diff_check=PASS
```

