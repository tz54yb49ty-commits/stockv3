# N2 Symmetry Target Price Alignment Golden Report

layer_role: N2_condition

execute: false
writes_performed: false

## Case

- identity: stock:SZ:000027
- code/name: 000027 深圳能源
- source_trade_date: 20260528
- for_trade_date: 20260529

## Golden Result

| Field | Expected | Actual |
|---|---:|---:|
| main_up_anchor | W | W |
| up_reference_period | D | D |
| A segment start | 20260506 | 20260506 |
| A segment end | 20260528 | 20260528 |
| segment_low | 6.88 | 6.88 |
| segment_high | 8.05 | 8.05 |
| amplitude | 1.17 | 1.17 |
| trend_break_date | 20260519 | 20260519 |
| base_window_start | 20260520 | 20260520 |
| base_window_end | 20260528 | 20260528 |
| base_price | 7.25 | 7.25 |
| buy_target_price | 8.42 | 8.42 |
| reference_target_price | 8.42 | 8.42 |

## Checks

- target_price_match: True
- trace_trend_break_match: True
- clear_sell_ref_period_alias_match: True
- forbidden_locked_fields_absent: True

## Full Dry-run Counts

| Stage | Stock | Index | Board |
|---|---:|---:|---:|
| condition_basis | 5506 | 83 | 428 |
| condition_pool | 4271 | 18 | 263 |
| minute_target_scope | 4271 | 18 | 263 |
| condition_display_basis | 2021 | 9 | 127 |

## Quality

- full dry-run P0/P1/P2: 0 / 3 / 3
- preflight execute_allowed: False
- preflight blocked_reasons: ['active_run_exists']

## Artifacts

- full dry-run JSON: docs/N2_symmetry_target_price_alignment_20260528_full_dry_run.json
- full dry-run MD: docs/N2_SYMMETRY_TARGET_PRICE_ALIGNMENT_20260528_FULL_DRY_RUN.md
- execute contract JSON: docs/N2_symmetry_target_price_alignment_20260528_execute_contract.json
- execute contract MD: docs/N2_SYMMETRY_TARGET_PRICE_ALIGNMENT_20260528_EXECUTE_CONTRACT.md
- execute preflight JSON: docs/N2_symmetry_target_price_alignment_20260528_full_execute_preflight.json
- execute preflight MD: docs/N2_SYMMETRY_TARGET_PRICE_ALIGNMENT_20260528_FULL_EXECUTE_PREFLIGHT.md

## Boundary Proof

- no active N2 execute performed
- no condition_* business rows written
- no N1 fact changes
- no market data pull
- no N3/N4/N5/N6 execution
- no outbox/inbox/checkpoint writes
