# N2-R3 After 012 Full Dry-Run Report

Date: 2026-05-24T20:46:47
Layer: N2_condition
Mode: full_dry_run_after_012_migration
Status: passed

## Date Context

```text
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
active index_daily = index_daily_20260522_v4
```

## Row Counts

| stage | stock | index | board | expected match |
|---|---:|---:|---:|---|
| condition_basis | 5504 | 81 | 428 | true |
| condition_pool | 4236 | 18 | 258 | true |
| minute_target_scope | 4236 | 18 | 258 | true |

## Reference Period Validation

Combined:

```text
up_sell_reference_period missing = 0
down_buy_reference_period missing = 0
clear_sell_ref_period missing = 0
clear_sell_ref_period != up_sell_reference_period = 0
invalid_reference_period = 0
```

| table | rows | expected | up missing | down missing | clear missing | alias mismatch | invalid |
|---|---:|---:|---:|---:|---:|---:|---:|
| `stock_condition_basis` | 5504 | 5504 | 0 | 0 | 0 | 0 | 0 |
| `index_condition_basis` | 81 | 81 | 0 | 0 | 0 | 0 | 0 |
| `board_condition_basis` | 428 | 428 | 0 | 0 | 0 | 0 | 0 |
| `stock_condition_pool` | 4236 | 4236 | 0 | 0 | 0 | 0 | 0 |
| `index_condition_pool` | 18 | 18 | 0 | 0 | 0 | 0 | 0 |
| `board_condition_pool` | 258 | 258 | 0 | 0 | 0 | 0 | 0 |
| `stock_minute_target_scope` | 4236 | 4236 | 0 | 0 | 0 | 0 | 0 |
| `index_minute_target_scope` | 18 | 18 | 0 | 0 | 0 | 0 | 0 |
| `board_minute_target_scope` | 258 | 258 | 0 | 0 | 0 | 0 | 0 |

## Fixed 9 Index Golden

```text
present_count = 9/9
matched_count = 9/9
passed = true
```

| code | identity | present | matched | BUY key | SELL key | up ref | down ref | clear alias |
|---|---|---|---|---|---|---|---|---|
| `000001` | `index:SH:000001` | true | true | BUY:W,D | SELL:Y,Q,M,D | W | D | W |
| `000016` | `index:SH:000016` | true | true | BUY:Y,Q,M,W,D | SELL:Y,Q,M,D | D | D | D |
| `000300` | `index:SH:000300` | true | true | BUY:W,D | SELL:Y,Q,M,D | W | D | W |
| `000688` | `index:SH:000688` | true | true | BUY:D | SELL:Y,Q,M,W,D | D | D | D |
| `000852` | `index:SH:000852` | true | true | BUY:W,D | SELL:Y,Q,M,W,D | W | D | W |
| `000905` | `index:SH:000905` | true | true | BUY:W,D | SELL:Y,Q,M,W,D | W | D | W |
| `399001` | `index:SZ:399001` | true | true | BUY:W,D | SELL:Y,Q,M,W,D | W | D | W |
| `399006` | `index:SZ:399006` | true | true | BUY:W,D | SELL:Y,Q,M,W,D | D | D | D |
| `399303` | `index:SZ:399303` | true | true | BUY:W,D | SELL:Y,Q,M,W,D | W | D | W |

## Quality

```text
basis P0/P1/P2 = 0/3/1
pool P0/P1/P2 = 0/1/1
scope P0/P1/P2 = 0/1/1
combined P0/P1/P2 = 0/5/3
```

The remaining P1/P2 warnings are inherited dry-run warnings, mainly the existing `for_trade_calendar_row_missing` P1 and static coverage samples. They are not N2-R3 reference-period blockers.

## Outbox / Active Run

```text
common_event_outbox before = 26652
common_event_outbox after = 26652
common_event_outbox unchanged = true
active_condition_run unchanged = true
```

## Checks

```text
basis_p0_zero = true
pool_p0_zero = true
scope_p0_zero = true
schema_missing_column_count_zero = true
row_counts_match_n2_r3_review = true
reference_period_full_chain_passed = true
fixed_9_index_golden_9_of_9 = true
common_event_outbox_unchanged = true
active_condition_run_unchanged = true
writes_performed_false = true
condition_pool_written_false = true
minute_kline_pulled_false = true
overwrite_executed = false
entered_N3_N4_N5_N6 = false
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
condition_overwrite_executed: no
condition_business_rows_written: no
```

## Artifacts

- basis_dry_run_json: `tmp/N2_R3_after_012_condition_basis_dry_run.json`
- pool_dry_run_json: `tmp/N2_R3_after_012_condition_pool_dry_run.json`
- scope_dry_run_json: `tmp/N2_R3_after_012_minute_target_scope_dry_run.json`
- pre_snapshot: `tmp/N2_R3_after_012_pre_snapshot.json`
- post_snapshot: `tmp/N2_R3_after_012_post_snapshot.json`
- schema_gap_after_012: `tmp/N2_R3_012_post_schema_gap.json`

## Next Step

Stop here. Execute N2-R3 overwrite only after explicit user confirmation.
