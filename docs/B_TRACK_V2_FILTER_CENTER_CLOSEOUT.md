# B Track V2 Filter Center Closeout

Gate: `B_TRACK_V2_FILTER_CENTER_CLOSEOUT_GATE`  
Layer role: `runtime_control`  
Result: `CLOSEOUT_PASS`  
Date: `2026-06-07`

This closeout registers completion of the B-track V2 filter-center source repair. It is documentation-only except for this artifact write. It does not write database rows, execute sync or migrations, consume/update outbox, start workers, generate proposal/order/trade, update position/PnL, submit real trade, or rollback the local display cache.

## Completed Repair Scope

The filter-center source boundary blocker is closed.

The repaired B-track V2 filter center now reads current official N6 readonly views:

| Filter area | Official read source |
|---|---|
| Stock filter | `v_n6_stock_condition_display_basis` |
| Index filter | `v_n6_index_condition_display_basis` |
| Board filter | `v_n6_board_condition_display_basis` |
| Index members | `v_n6_index_membership_fact` |
| Board members | `v_n6_board_membership_fact` |

The UI/API source labels remain B-track logical display labels:

| Filter area | Display source label |
|---|---|
| Stock filter | `n6_display_stock_condition_cache` |
| Index filter | `n6_display_index_condition_cache` |
| Board filter | `n6_display_board_condition_cache` |
| Index members | `n6_display_index_membership_cache` |
| Board members | `n6_display_board_membership_cache` |

## Source Boundary Proof

- Filter-center repository reads `v_n6_*` readonly views.
- Filter-center repository does not read local display cache physical tables:
  - `n6_stock_display_cache`
  - `n6_index_display_cache`
  - `n6_board_display_cache`
  - `n6_index_membership_display_cache`
  - `n6_board_membership_display_cache`
- Filter-center repository does not directly read base display-basis tables:
  - `stock_condition_display_basis`
  - `index_condition_display_basis`
  - `board_condition_display_basis`
- Filter-center repository does not read `condition_basis`, `condition_pool`, `minute_target_scope`, raw K, N4/N5 raw facts, or outbox.

## Row Count Proof

The repaired filter-center source grain matches N2 display-basis source rows, not the experimental local-cache fanout rows:

| Source | Row count |
|---|---:|
| `v_n6_stock_condition_display_basis` | 1,952 |
| `v_n6_index_condition_display_basis` | 9 |
| `v_n6_board_condition_display_basis` | 428 |
| `v_n6_index_membership_fact` | 12,841 |
| `v_n6_board_membership_fact` | 56,960 |

No direction/condition cartesian fanout is performed:

```text
invalid_direction_condition_fanout_rows_generated = 0
cross_join_used = false
unnest_used = false
jsonb_array_elements_used = false
```

Period filters use direct readonly-view columns:

```text
year_overheat_level    -> period_grade_y
quarter_overheat_level -> period_grade_q
month_overheat_level   -> period_grade_m
week_overheat_level    -> period_grade_w
day_overheat_level     -> period_grade_d
```

## Local Cache Status

The current local display cache remains present but is not a valid source for B-track V2 filter center.

```text
status_for_b_track_filter_center = experimental/tainted_for_b_track_filter_center
rollback_executed_in_this_gate = false
used_by_filter_center = false
```

If database cleanup is needed later, use a separate gate:

```text
N6_LOCAL_DISPLAY_CACHE_SEMANTIC_TAINTED_ROLLBACK_FINAL_GATE
```

## Validation

Fresh post-review validation registered:

- `tests/test_n6_user_app.py`: PASS, 78 tests.
- Implementation JSON parse: PASS.
- Targeted `git diff --check`: PASS.
- V2 filter routes remain GET-only.
- Forbidden source scan: PASS.
- No-fanout assertion: PASS.

## Residual Notes

- This closeout covers only `/api/n6/app/v2/filter/*` and `/n6/app/filter-center`.
- Separate non-filter dashboard helpers still have legacy base display-basis reads in `fetch_top_index_strategy` and `fetch_strong_boards`. They are outside this closeout scope and should be handled by a later source-boundary cleanup gate.
- If the user requires Excel/base-table full field coverage in B-track, open a separate readonly view widening gate rather than reading base tables directly.

## Next Recommended Gate

```text
B_TRACK_V2_DASHBOARD_SOURCE_BOUNDARY_CLEANUP_PLAN_GATE
```

Alternative optional cleanup gate:

```text
N6_LOCAL_DISPLAY_CACHE_SEMANTIC_TAINTED_ROLLBACK_FINAL_GATE
```

