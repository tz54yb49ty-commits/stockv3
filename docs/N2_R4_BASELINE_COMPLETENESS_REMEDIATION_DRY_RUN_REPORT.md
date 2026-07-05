# N2-R4 Baseline Completeness Remediation Dry-Run Report

layer_role = N2_condition
status = passed

## Scope

This dry-run verifies the N2-R4 baseline completeness remediation after 013 migration. It does not overwrite active condition runs and does not write condition business rows.

```text
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
```

## Artifacts

- source_ready: `tmp/N2_R4_baseline_completeness_condition_source_ready_20260522.txt`
- basis_dry_run: `tmp/N2_R4_baseline_completeness_condition_basis_dry_run.json`
- pool_dry_run: `tmp/N2_R4_baseline_completeness_condition_pool_dry_run.json`
- scope_dry_run: `tmp/N2_R4_baseline_completeness_minute_target_scope_dry_run.json`
- outbox_before: `tmp/N2_R4_baseline_completeness_outbox_before.txt`
- outbox_after: `tmp/N2_R4_baseline_completeness_outbox_after.txt`
- json_report: `docs/N2_R4_BASELINE_COMPLETENESS_REMEDIATION_DRY_RUN_REPORT.json`

## Row Counts

| Stage | stock | index | board | P0/P1/P2 |
|---|---:|---:|---:|---:|
| condition_basis | 5504 | 81 | 428 | 0/4/1 |
| condition_pool | 4236 | 18 | 258 | 0/1/1 |
| minute_target_scope | 4236 | 18 | 258 | 0/1/1 |

## Baseline Coverage

| Stage | Domain | baseline_missing | invalid_shape | all_period_not_ready_rows | required_period_not_ready_rows |
|---|---|---:|---:|---:|---:|
| condition_basis | stock | 0 | 0 | 62 | n/a |
| condition_basis | index | 0 | 0 | 0 | n/a |
| condition_basis | board | 0 | 0 | 1 | n/a |
| condition_pool | stock | 0 | 0 | 40 | 0 |
| condition_pool | index | 0 | 0 | 0 | 0 |
| condition_pool | board | 0 | 0 | 0 | 0 |
| minute_target_scope | stock | 0 | 0 | 40 | 0 |
| minute_target_scope | index | 0 | 0 | 0 | 0 |
| minute_target_scope | board | 0 | 0 | 0 | 0 |

`condition_basis` remains a full audit root, so all-period baseline gaps are retained as warning diagnostics. `condition_pool` and `minute_target_scope` are validated by condition_key required periods.

## Fixed 9 Index

| Stage | present | valid_shape | ready |
|---|---:|---:|---:|
| condition_basis | 9/9 | 9/9 | 9/9 |
| condition_pool | 9/9 | 9/9 | 9/9 |
| minute_target_scope | 9/9 | 9/9 | 9/9 |

## Event / Write Guard

```text
common_event_outbox: 26652 -> 26652
overwrite_executed=false
migration_executed=false
condition_business_rows_written=false
entered_N3_N4_N5_N6=false
market_data_pulled=false
old_system_touched=false
```

## Acceptance

```text
N2_R4_baseline_completeness_passed = true
N2_R4_baseline_completeness_P0/P1/P2 = 0/0/0
can_enter_n2_r4_overwrite = true
```
