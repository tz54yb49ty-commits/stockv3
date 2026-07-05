# A1 Opening Prep 20260601 Test Completion Report

Result: `N1_PRODUCTION_PASS_N2_N3_A1_TEST_ENV_PASS`

This report applies the user-confirmed fallback order:

```text
mock -> dry-run -> preflight -> test environment -> production
```

N1 official daily production ingestion was executed after user confirmation and passed post-review. N2/N3 production executes were not run in this step.

## N1

```text
opening_prep_source_status = PASS
calendar 20260601 = exists / is_open=true
prev_trade_date = 20260529
next_trade_date = 20260602
calendar source_version = trade_calendar_20260601_patch_v1
```

Production official daily facts for `20260601` are written and post-reviewed:

```text
stock_daily_bar_fact = 5508
index_daily_bar_fact = 83
board_daily_bar_fact = 428
total_daily_fact = 6019
```

Post-review artifacts:

```text
json = docs/N1_official_daily_20260601_ingestion_execute_post_review.json
md = docs/N1_OFFICIAL_DAILY_20260601_INGESTION_EXECUTE_POST_REVIEW.md
source_batch_id = official_daily_ingest_20260601_v1
active source_versions = stock_daily_20260601_v1 / index_daily_20260601_v1 / board_daily_20260601_v1
P0/P1/P2 = 0/18/0
rollback_safe = true
rollback = sql/N1_official_daily_20260601_ingestion_rollback.sql
```

For A1 opening prep, downstream N2/N3 input still uses the completed `20260529 -> 20260601` condition lineage. The N1 20260601 official daily facts are now available for day-end / next-chain use.

Additional N1 read-only source probe:

```text
artifact = docs/N1_official_daily_20260601_stock_source_probe.json
result = STOCK_PROBE_PASS
tushare_daily_count = 5508
adj_factor_count = 5525
matched_identity_count = 5508
unmapped_count = 0
P0/P1/P2 = 0/1/0
writes_performed = false
```

The earlier deferred index/board source P1 has been cleared by a full read-only probe.

Additional N1 read-only index/board full probe:

```text
artifact = docs/N1_official_daily_20260601_index_board_source_probe.json
result = FULL_PROBE_PASS
selected index/board = 83/428
source index/board = 83/428
P0/P1/P2 = 0/0/0
writes_performed = false
```

N1 official daily 20260601 gate artifacts have also been prepared:

```text
dry_run = docs/N1_official_daily_20260601_ingestion_dry_run_report.json
contract = docs/N1_official_daily_20260601_ingestion_execute_contract.json
preflight = docs/N1_official_daily_20260601_ingestion_execute_preflight.json
final_gate = docs/N1_official_daily_20260601_ingestion_final_gate.json
rollback = sql/N1_official_daily_20260601_ingestion_rollback.sql
dry_run_result = DRY_RUN_PASS_WITH_DEFERRED_FINAL_SOURCE_PROBE
preflight_result = PREFLIGHT_PASS
final_gate_result = PASS
production_execute_allowed = false
final_execute_gate_allowed = true
expected rows stock/index/board/total = 5508/83/428/6019
preflight P0/P1/P2 = 0/0/0
```

Production N1 execute has been completed after explicit user confirmation. No automatic N2/N3 execute was performed.

Current runner status:

```text
script = scripts/run_official_daily_ingestion_20260601_once.py
runner_readiness = ready_for_final_gate
nonproduction artifact refresh = implemented
production commit path = implemented_guarded_by_four_flags
```

## N2

```text
active_condition_run_id = condition_layer_20260529_source_20260529_v6
status = passed_active
source_trade_date = 20260529
for_trade_date = 20260601
```

N2 is ready for 20260601 opening-prep handoff.

## N3

Subscription and previous-day preload are already passed:

```text
subscription = market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6
subscription_status = passed
previous_day_preload = previous_day_minute_preload_20260529_for_20260601__market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6
previous_day_preload_status = passed
```

B0/B1 test-environment artifacts:

```text
B0 test dry-run blocked = false
B0 expected snapshot rows = 2373
B0 expected stock/index/board = 1862/83/428
B0 P0/P1/P2 = 0/1/0

B1 test execute contract P0/P1/P2 = 0/1/0
B1 writes_outbox = false
B1 rollback_sql = sql/N3_B1_realtime_snapshot_20260601_a1_test_rollback.sql

B1 test readiness current_date_override = 20260601
B1 test readiness ready = true
B1 test readiness P0/P1/P2 = 0/0/0
```

Production B1 realtime snapshot was not executed:

```text
snapshot rows stock/index/board = 0/0/0
outbox rows for test snapshot run = 0
```

## Boundaries

```text
n1 official daily fact writes in this completion step = true
condition_* writes in this completion step = false
market data fact writes in this completion step = false
event outbox writes in this completion step = false
N4/N5/N6 entered = false
worker_started = false
old_system_touched = false
real_trading_touched = false
```

## Remaining Production Confirmation Points

```text
1. N3 B1 realtime snapshot production execute, if production snapshot rows are required.
2. Any N4/N5/N6 follow-up.
```
