# N2 20260529 Symmetry Target Price v3 Execute Post Review

status: POST_REVIEW_PASS

## Run Status

| run_id | status |
|---|---|
| condition_layer_20260529_source_20260529_v2 | superseded |
| condition_layer_20260529_source_20260529_v3 | passed_active |

## Row Counts

```json
{
  "condition_basis": {
    "board": 428,
    "index": 83,
    "stock": 5506
  },
  "condition_display_basis": {
    "board": 428,
    "index": 83,
    "stock": 1862
  },
  "condition_pool": {
    "board": 942,
    "index": 187,
    "stock": 4106
  },
  "minute_target_scope": {
    "board": 942,
    "index": 187,
    "stock": 4087
  },
  "monitor_target": {
    "board": 428,
    "index": 83,
    "stock": 5506
  }
}
```

## Golden Targets

### 000543 皖能电力

| field | value |
|---|---|
| main_up_anchor | W |
| up_reference_period | D |
| a_segment_start_date | 20260506 |
| a_segment_end_date | 20260529 |
| a_segment_low | 8.09 |
| a_segment_high | 9.8 |
| a_segment_amplitude | 1.71 |
| trend_break_date | 20260526 |
| up_reference_window_start | 20260527 |
| up_reference_window_end | 20260529 |
| base_price | 9.11 |
| buy_target_price | 10.82 |
| reference_target_price | 10.82 |
| secondary_target_price | None |
| trace_policy | OFFICIAL_HIGH_LOW |

### 000027 深圳能源

| field | value |
|---|---|
| main_up_anchor | W |
| up_reference_period | D |
| a_segment_start_date | 20260506 |
| a_segment_end_date | 20260529 |
| a_segment_low | 6.88 |
| a_segment_high | 8.08 |
| a_segment_amplitude | 1.2 |
| trend_break_date | 20260519 |
| up_reference_window_start | 20260520 |
| up_reference_window_end | 20260529 |
| base_price | 7.25 |
| buy_target_price | 8.45 |
| reference_target_price | 8.45 |
| secondary_target_price | None |
| trace_policy | OFFICIAL_HIGH_LOW |


## Quality

```json
{
  "p0_p1_p2": {
    "P0": 0,
    "P1": 6,
    "P2": 3
  },
  "quality_by_severity_status": [
    {
      "count": 91,
      "severity": "P0",
      "status": "passed"
    },
    {
      "count": 3,
      "severity": "P1",
      "status": "passed"
    },
    {
      "count": 8,
      "severity": "P1",
      "status": "warning"
    },
    {
      "count": 4,
      "severity": "P2",
      "status": "warning"
    }
  ],
  "quality_rows": 106
}
```

## Boundary Proof

event_delta: {'outbox': 0, 'inbox': 0, 'checkpoint': 0}
downstream_ref_total: 0
rollback_safe: True

rollback_sql: `sql/N2_symmetry_target_price_target_machine_alignment_20260529_rollback.sql`
