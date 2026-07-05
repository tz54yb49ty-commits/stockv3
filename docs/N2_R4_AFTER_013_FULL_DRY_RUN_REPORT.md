# N2-R4 After 013 Full Dry-Run Report

layer_role = N2_condition
status = failed_acceptance

## Scope

This run rechecked the N2 condition dry-run chain after 013 migration. It did not overwrite the active condition run and did not write condition business rows.

```text
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
```

## Artifacts

- source_ready: `tmp/N2_R4_after_013_condition_source_ready_20260522.txt`
- schema_gap: `tmp/N2_R4_after_013_schema_gap_report.json`
- basis_dry_run: `tmp/N2_R4_after_013_condition_basis_dry_run.json`
- pool_dry_run: `tmp/N2_R4_after_013_condition_pool_dry_run.json`
- scope_dry_run: `tmp/N2_R4_after_013_minute_target_scope_dry_run.json`
- json_report: `docs/N2_R4_after_013_full_dry_run_report.json`

## Dry-Run Quality

| Stage | P0/P1/P2 | Passed | Rows |
|---|---:|---|---|
| condition_basis | 0/3/1 | True | stock=5504 index=81 board=428 |
| condition_pool | 0/1/1 | True | stock=4236 index=18 board=258 |
| minute_target_scope | 0/1/1 | True | stock=4236 index=18 board=258 |

Script-level dry-run P0 remains 0, but N2-R4 acceptance fails on the stricter previous entity bound check below.

## Baseline Coverage

| Stage | Domain | Rows | baseline_missing | invalid_shape | previous_entity_high_low_missing_rows |
|---|---|---:|---:|---:|---:|
| condition_basis | stock | 5504 | 0 | 0 | 62 |
| condition_basis | index | 81 | 0 | 0 | 0 |
| condition_basis | board | 428 | 0 | 0 | 1 |
| condition_pool | stock | 4236 | 0 | 0 | 40 |
| condition_pool | index | 18 | 0 | 0 | 0 |
| condition_pool | board | 258 | 0 | 0 | 0 |
| minute_target_scope | stock | 4236 | 0 | 0 | 40 |
| minute_target_scope | index | 18 | 0 | 0 | 0 |
| minute_target_scope | board | 258 | 0 | 0 | 0 |

## Fixed 9 Index

| Stage | present | valid_shape | previous_entity_complete |
|---|---:|---:|---:|
| condition_basis | 9/9 | 9/9 | 9/9 |
| condition_pool | 9/9 | 9/9 | 9/9 |
| minute_target_scope | 9/9 | 9/9 | 9/9 |

## Failed Acceptance Check

The field exists and is JSON-parseable throughout the chain, but some rows still have missing `previous_entity_high` / `previous_entity_low` inside the baseline JSON.

Representative samples:

```json
{
  "condition_basis_stock": [
    {
      "identity_key": "stock:BJ:920011",
      "code": "920011",
      "name": "晨光电机",
      "condition_key": null,
      "missing_periods": [
        "Y",
        "Q"
      ],
      "quality_status": "warning",
      "amount_quality_status": "warning"
    },
    {
      "identity_key": "stock:BJ:920012",
      "code": "920012",
      "name": "创达新材",
      "condition_key": null,
      "missing_periods": [
        "Y",
        "Q"
      ],
      "quality_status": "warning",
      "amount_quality_status": "warning"
    },
    {
      "identity_key": "stock:BJ:920028",
      "code": "920028",
      "name": "新恒泰",
      "condition_key": null,
      "missing_periods": [
        "Y"
      ],
      "quality_status": "warning",
      "amount_quality_status": "warning"
    }
  ],
  "condition_basis_board": [
    {
      "identity_key": "board:TDX:880958",
      "code": "880958",
      "name": "AI营销",
      "condition_key": null,
      "missing_periods": [
        "Y"
      ],
      "quality_status": "warning",
      "amount_quality_status": "warning"
    }
  ],
  "condition_pool_stock": [
    {
      "identity_key": "stock:BJ:920178",
      "code": "920178",
      "name": "锐翔智能",
      "condition_key": "BUY:W,D",
      "missing_periods": [
        "Y",
        "Q",
        "M"
      ],
      "quality_status": "warning",
      "amount_quality_status": null
    },
    {
      "identity_key": "stock:BJ:920178",
      "code": "920178",
      "name": "锐翔智能",
      "condition_key": "SELL:W",
      "missing_periods": [
        "Y",
        "Q",
        "M"
      ],
      "quality_status": "warning",
      "amount_quality_status": null
    },
    {
      "identity_key": "stock:BJ:920186",
      "code": "920186",
      "name": "中科仪",
      "condition_key": "BUY:M,W,D",
      "missing_periods": [
        "Y",
        "Q"
      ],
      "quality_status": "warning",
      "amount_quality_status": null
    }
  ],
  "minute_target_scope_stock": [
    {
      "identity_key": "stock:BJ:920178",
      "code": "920178",
      "name": "锐翔智能",
      "condition_key": "BUY:W,D",
      "missing_periods": [
        "Y",
        "Q",
        "M"
      ],
      "quality_status": null,
      "amount_quality_status": null
    },
    {
      "identity_key": "stock:BJ:920178",
      "code": "920178",
      "name": "锐翔智能",
      "condition_key": "SELL:W",
      "missing_periods": [
        "Y",
        "Q",
        "M"
      ],
      "quality_status": null,
      "amount_quality_status": null
    },
    {
      "identity_key": "stock:BJ:920186",
      "code": "920186",
      "name": "中科仪",
      "condition_key": "BUY:M,W,D",
      "missing_periods": [
        "Y",
        "Q"
      ],
      "quality_status": null,
      "amount_quality_status": null
    }
  ]
}
```

## Event / Write Guard

```text
common_event_outbox: 26652 -> 26652
overwrite_executed=false
condition_business_rows_written=false
entered_N3_N4_N5_N6=false
market_data_pulled=false
old_system_touched=false
```

## Acceptance

```text
N2_R4_acceptance_passed = false
N2_R4_acceptance_P0/P1/P2 = 1/0/0
can_enter_n2_r4_overwrite = false
```

Do not execute N2-R4 overwrite until the `previous_entity_high` / `previous_entity_low` gaps are remediated or the acceptance policy is explicitly revised.
