# N2-R3 Overwrite Execute Report

Date: 2026-05-24T21:03:57
Layer: N2_condition
Mode: overwrite_execute_after_012_full_dry_run
Status: passed

## Summary

```text
execute_run_id = condition_layer_20260522_to_20260525_20260524205747_execute
previous_active_run_id = condition_layer_20260522_to_20260525_20260524181321_execute
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
new_run_status = passed
old_run_status = superseded
active_passed_run_count = 1
```

## New Run Row Counts

| table | expected | actual | matches |
|---|---:|---:|---|
| `stock_condition_basis` | 5504 | 5504 | true |
| `index_condition_basis` | 81 | 81 | true |
| `board_condition_basis` | 428 | 428 | true |
| `stock_condition_pool` | 4236 | 4236 | true |
| `index_condition_pool` | 18 | 18 | true |
| `board_condition_pool` | 258 | 258 | true |
| `stock_minute_target_scope` | 4236 | 4236 | true |
| `index_minute_target_scope` | 18 | 18 | true |
| `board_minute_target_scope` | 258 | 258 | true |
| `stock_monitor_target` | 5504 | 5504 | true |
| `index_monitor_target` | 81 | 81 | true |
| `board_monitor_target` | 428 | 428 | true |
| `common_condition_quality_item` | 70 | 70 | true |
| `common_condition_run` | 1 | 1 | true |

## Reference Period Validation

```text
up_sell_reference_period missing = 0
down_buy_reference_period missing = 0
clear_sell_ref_period missing = 0
clear_sell_ref_period != up_sell_reference_period = 0
invalid_reference_period = 0
```

| table | rows | up missing | down missing | clear missing | alias mismatch | invalid |
|---|---:|---:|---:|---:|---:|---:|
| `stock_condition_basis` | 5504 | 0 | 0 | 0 | 0 | 0 |
| `index_condition_basis` | 81 | 0 | 0 | 0 | 0 | 0 |
| `board_condition_basis` | 428 | 0 | 0 | 0 | 0 | 0 |
| `stock_condition_pool` | 4236 | 0 | 0 | 0 | 0 | 0 |
| `index_condition_pool` | 18 | 0 | 0 | 0 | 0 | 0 |
| `board_condition_pool` | 258 | 0 | 0 | 0 | 0 | 0 |
| `stock_minute_target_scope` | 4236 | 0 | 0 | 0 | 0 | 0 |
| `index_minute_target_scope` | 18 | 0 | 0 | 0 | 0 | 0 |
| `board_minute_target_scope` | 258 | 0 | 0 | 0 | 0 | 0 |

## Fixed 9 Index Golden

```text
present_count = 9/9
matched_count = 9/9
passed = true
```

| code | identity | matched | BUY key | SELL key | up ref | down ref | clear alias |
|---|---|---|---|---|---|---|---|
| `000001` | `index:SH:000001` | true | BUY:W,D | SELL:Y,Q,M,D | W | D | W |
| `000016` | `index:SH:000016` | true | BUY:Y,Q,M,W,D | SELL:Y,Q,M,D | D | D | D |
| `000300` | `index:SH:000300` | true | BUY:W,D | SELL:Y,Q,M,D | W | D | W |
| `000688` | `index:SH:000688` | true | BUY:D | SELL:Y,Q,M,W,D | D | D | D |
| `000852` | `index:SH:000852` | true | BUY:W,D | SELL:Y,Q,M,W,D | W | D | W |
| `000905` | `index:SH:000905` | true | BUY:W,D | SELL:Y,Q,M,W,D | W | D | W |
| `399001` | `index:SZ:399001` | true | BUY:W,D | SELL:Y,Q,M,W,D | W | D | W |
| `399006` | `index:SZ:399006` | true | BUY:W,D | SELL:Y,Q,M,W,D | D | D | D |
| `399303` | `index:SZ:399303` | true | BUY:W,D | SELL:Y,Q,M,W,D | W | D | W |

## Outbox / Run Status

```text
common_event_outbox before = 26652
common_event_outbox after = 26652
common_event_outbox unchanged = true
active passed run count = 1
```

## Checks

```text
after_012_full_dry_run_passed = true
after_012_full_dry_run_p0_zero = true
execute_run_status_passed = true
active_passed_run_count_one = true
new_run_status_passed = true
old_run_status_superseded = true
run_row_counts_match_dry_run = true
condition_total_deltas_match_dry_run = true
reference_period_full_chain_passed = true
fixed_9_index_golden_9_of_9 = true
common_event_outbox_unchanged = true
migration_performed_false = true
minute_kline_pulled_false = true
downstream_layers_touched_false = true
rollback_sql_generated = true
P0/P1/P2 = 0/5/3
```

## Rollback

Rollback SQL: `sql/N2_R3_overwrite_rollback.sql`

Rollback was generated but not executed.

## Validation

```text
python3 -m compileall scripts src tests: passed
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_condition_basis.py': passed, 10 tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_condition_static_reference_period_chain.py': passed, 5 tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n2_web_policy.py': passed, 23 tests
git diff --check: passed
forbidden field scan: no new N2 formal field hit; only existing docs prohibition text
```

## Boundary

```text
old_system_touched: no
external_market_api_called: no
minute_k_pulled: no
worker_started: no
entered_N3_N4_N5_N6: no
common_event_outbox_written: no
n1_fact_modified: no
condition_overwrite_executed: yes
condition_business_rows_written: yes
```

## Artifacts

- pre_snapshot: `backups/N2_R3_overwrite_before_snapshot_20260524.json`
- post_snapshot: `backups/N2_R3_overwrite_after_snapshot_20260524.json`
- raw_execute_report: `tmp/N2_R3_overwrite_execute_raw.json`
- dry_run_report: `docs/N2_R3_after_012_full_dry_run_report.json`
- rollback_sql: `sql/N2_R3_overwrite_rollback.sql`

## Next Step

Stop here. Do not enter N3/N4/N5/N6 without explicit user confirmation.
