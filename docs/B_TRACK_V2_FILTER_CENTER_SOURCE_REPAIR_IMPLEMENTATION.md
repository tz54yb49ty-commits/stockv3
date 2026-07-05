# B Track V2 Filter Center Source Repair Implementation

Gate: `B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION_GATE`  
Layer role: `N6_user`  
Result: `IMPLEMENTATION_PASS`  
Date: `2026-06-07`

## Scope

This gate repairs only the B-track V2 filter center read boundary.

No database writes, schema execution, outbox consumption/update, worker startup, proposal/order/trade generation, position/PnL update, or real trade submission was performed.

## Modified Files

- `src/ashare_v3/web/n6_user_app.py`
- `src/ashare_v3/web/n6_app_v1.py`
- `tests/test_n6_user_app.py`
- `docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION.md`
- `docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION.json`

## Source Repair

The B-track V2 filter repository now reads official N6 readonly views:

| API Path | Read Source |
|---|---|
| `GET /api/n6/app/v2/filter/stocks` | `v_n6_stock_condition_display_basis` |
| `GET /api/n6/app/v2/filter/indexes` | `v_n6_index_condition_display_basis` |
| `GET /api/n6/app/v2/filter/boards` | `v_n6_board_condition_display_basis` |
| `GET /api/n6/app/v2/filter/index-members` | `v_n6_index_membership_fact` |
| `GET /api/n6/app/v2/filter/board-members` | `v_n6_board_membership_fact` |

The B-track API/UI source labels remain logical display labels only:

- `n6_display_stock_condition_cache`
- `n6_display_index_condition_cache`
- `n6_display_board_condition_cache`
- `n6_display_index_membership_cache`
- `n6_display_board_membership_cache`

The experimental local physical cache tables remain marked as not used by the filter center.

## Field Strategy

- `selected_directions`, `selected_condition_keys`, `selected_signal_types`, `selected_lanes`, and `selected_monitor_types` are preserved as arrays.
- No direction/condition fanout is performed.
- Period filters now use direct columns: `period_grade_y`, `period_grade_q`, `period_grade_m`, `period_grade_w`, `period_grade_d`.
- Existing table UI summary fields are retained as display summaries only.

## Row Count Proof

Latest readonly view row counts:

| Source | Count |
|---|---:|
| `v_n6_stock_condition_display_basis` | 1952 |
| `v_n6_index_condition_display_basis` | 9 |
| `v_n6_board_condition_display_basis` | 428 |
| `v_n6_index_membership_fact` | 12841 |
| `v_n6_board_membership_fact` | 56960 |

## Forbidden Source Proof

The repaired filter-center repository path does not read:

- `n6_stock_display_cache`
- `n6_index_display_cache`
- `n6_board_display_cache`
- `n6_index_membership_display_cache`
- `n6_board_membership_display_cache`
- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `condition_basis`
- `condition_pool`
- `minute_target_scope`
- raw K
- N4/N5 raw facts
- outbox

## Validation

- Targeted repository source-boundary test: PASS
- `tests/test_n6_user_app.py`: PASS, 78 tests
- Readonly DB row count assertion: PASS
- No fanout assertion: PASS
- V2 route scan GET-only: PASS

## Next Gate

Return to `runtime_control` for:

```text
B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_POST_REVIEW_GATE
```
