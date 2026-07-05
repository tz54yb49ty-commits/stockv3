# N1 Official Daily 20260601 Stock Source Probe

Result: `STOCK_PROBE_PASS`

This is a read-only source probe. It did not write PostgreSQL facts, Parquet, condition tables, outbox/inbox/checkpoint, or downstream layers.

```text
trade_date = 20260601
calendar = exists / is_open=true
prev_trade_date = 20260529
next_trade_date = 20260602
calendar_source_version = trade_calendar_20260601_patch_v1
```

DB baseline:

```text
stock_daily_bar_fact = 0
index_daily_bar_fact = 0
board_daily_bar_fact = 0
batch_conflict = 0
quality_conflict = 0
active_conflict = 0
```

Stock source coverage:

```text
active_stock_identity_count = 5526
tushare_daily_count = 5508
adj_factor_count = 5525
matched_identity_count = 5508
unmapped_count = 0
duplicate_daily_ts_code_count = 0
adj_minus_daily_active_identity_count = 17
P0/P1/P2 = 0/1/0
```

The P1 item is intentional:

```text
index_board_source_probe_deferred_to_final_gate
```

Deferred to production final gate:

```text
index source coverage probe
board source coverage probe
official_daily_20260601 execute runner implementation/reuse decision
production PostgreSQL commit
```

Boundary proof:

```text
postgres_fact_written = false
parquet_written = false
condition_tables_written = false
entered_N2_N6 = false
worker_started = false
old_system_touched = false
real_trading_touched = false
```
