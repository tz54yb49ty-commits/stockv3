# N2-R4 Period Trigger Baseline Full-Chain Dry-Run Report

Generated: 2026-05-24T23:35:37
Layer: N2_condition
Mode: dry-run only, no migration, no overwrite

## Summary

```text
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
source_ready_passed = True
basis P0/P1/P2 = 0/3/1
pool P0/P1/P2 = 0/1/1
scope P0/P1/P2 = 0/1/1
passed = true
```

## Row Counts

| stage | stock | index | board |
|---|---:|---:|---:|
| basis | 5504 | 81 | 428 |
| pool | 4236 | 18 | 258 |
| scope | 4236 | 18 | 258 |
| scope objects | 2052 | 9 | 127 |

## Baseline Coverage

| stage | domain | rows | valid_shape | missing |
|---|---|---:|---:|---:|
| basis | stock | 5504 | 5504 | 0 |
| basis | index | 81 | 81 | 0 |
| basis | board | 428 | 428 | 0 |
| pool | stock | 4236 | 4236 | 0 |
| pool | index | 18 | 18 | 0 |
| pool | board | 258 | 258 | 0 |
| scope | stock | 4236 | 4236 | 0 |
| scope | index | 18 | 18 | 0 |
| scope | board | 258 | 258 | 0 |

## Fixed 9 Index Baseline

```text
object_count = 9
valid_baseline_count = 9
```

## Boundary

```text
migration_executed: no
overwrite_executed: no
condition_tables_written: no
market_data_pulled: no
minute_kline_pulled: no
entered_N3_N4_N5_N6: no
worker_started: no
old_system_touched: no
```

## Artifacts

- ready_check: `tmp/N2_R4_condition_source_ready_20260522.json`
- basis_dry_run: `tmp/N2_R4_condition_basis_dry_run.json`
- pool_dry_run: `tmp/N2_R4_condition_pool_dry_run.json`
- scope_dry_run: `tmp/N2_R4_minute_target_scope_dry_run.json`

Stop here. Do not execute migration, overwrite, or enter N3/N4/N5/N6 without explicit user confirmation.
