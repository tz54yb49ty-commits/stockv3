# N1 Trade Calendar 20260608 Patch Post-Review

Result: `POST_REVIEW_PASS`

Generated at: `2026-06-07T18:41:17+08:00`

## Calendar

| item | value |
|---|---|
| trade_date | `20260608` |
| exchange | `SSE` |
| is_open | `true` |
| prev_trade_date | `20260605` |
| next_trade_date | `20260609` |
| source | `tushare.trade_cal.patch` |
| source_batch_id | `trade_calendar_20260608_patch_v1` |
| source_version | `trade_calendar_20260608_patch_v1` |

## DB Rows

| table/scope | rows |
|---|---:|
| common_trade_calendar(20260608) | 1 |
| common_active_source_version(SSE:20260608) | 1 |
| common_ingest_batch | 1 |
| common_quality_gate_result | 11 |
| stock_daily_bar_fact(20260608) | 0 |
| index_daily_bar_fact(20260608) | 0 |
| board_daily_bar_fact(20260608) | 0 |

## Quality

```text
P0/P1/P2 = 0/0/0
quality_by_severity_status = P0:passed 11
```

## Boundary

```text
daily_fact_written = false
market_data_pulled = false
condition_source_written = false
N2/N3/N4/N5/N6 entered = false
worker_started = false
parquet_written = false
old_system_touched = false
real_trading = false
outbox/inbox/checkpoint delta = 0/0/0
```

## Rollback

```text
rollback_safe = true
rollback_sql = sql/N1_trade_calendar_20260608_patch_rollback.sql
hard_fail_before_delete = true
rollback refs: outbox/inbox/checkpoint/N2/N3/N4/N5/N6 = 0/0/0/0/0/0/0/0
```

## Next Gate

The calendar patch is complete. The full `20260605 close -> 20260608 premarket`
repair remains blocked until guarded 20260605 official daily and condition source
runner/contracts are ready. Do not enter N2/N3/N4/N5/N6 from this gate.
