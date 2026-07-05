# N2 Symmetry Target Price Alignment Execute Preflight

layer_role: N2_condition

execute: false
writes_performed: false

## Result

- execute_allowed_read_only_preflight: True
- blocked_reasons: []
- requested_run_id: condition_layer_20260528_source_20260528_target_alignment_dry_run
- will_execute_sql: False
- writes_performed: False
- n3_lineage_auto_switch: False

## Expected Row Counts

```json
{
  "common_condition_run": 1,
  "common_condition_quality_item": 75,
  "stock_monitor_target": 5506,
  "index_monitor_target": 83,
  "board_monitor_target": 428,
  "stock_condition_basis": 5506,
  "index_condition_basis": 83,
  "board_condition_basis": 428,
  "stock_condition_pool": 4271,
  "index_condition_pool": 169,
  "board_condition_pool": 875,
  "index_minute_target_scope": 169,
  "board_minute_target_scope": 875,
  "stock_minute_target_scope": 4251
}
```

## Quality

```json
{
  "p0_count": 0,
  "p1_count": 3,
  "p2_count": 3
}
```

## Golden Report

- docs/N2_symmetry_target_price_alignment_20260528_golden_report.json
- docs/N2_SYMMETRY_TARGET_PRICE_ALIGNMENT_20260528_GOLDEN_REPORT.md

## Boundary

This is a read-only preflight artifact. It does not authorize an active N2 run.
