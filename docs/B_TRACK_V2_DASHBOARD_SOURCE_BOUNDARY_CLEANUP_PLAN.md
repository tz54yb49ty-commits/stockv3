# B Track V2 Dashboard Source Boundary Cleanup Plan

Gate: `B_TRACK_V2_DASHBOARD_SOURCE_BOUNDARY_CLEANUP_PLAN_GATE`  
Layer role: `runtime_control`  
Result: `PLAN_PASS`  
Date: `2026-06-07`

This is a documentation-only cleanup plan. It does not modify code, write database rows, execute migrations or sync, consume/update outbox, start workers, rollback local display cache, generate proposal/order/trade, update position/PnL, or submit real trade.

## Background

`B_TRACK_V2_FILTER_CENTER_CLOSEOUT_GATE` closed the filter-center source-boundary blocker:

- Filter center reads official `v_n6_*` readonly views.
- `n6_display_*_cache` remains a UI/API logical source label only.
- Experimental local display cache physical tables remain `experimental/tainted_for_b_track_filter_center`.

During closeout, two non-filter B-track repository helpers still showed legacy direct reads from N2 base display-basis tables:

| Helper | Current source | Target source | Scope |
|---|---|---|---|
| `fetch_top_index_strategy` | `index_condition_display_basis` | `v_n6_index_condition_display_basis` | B-track dashboard/home summary helper |
| `fetch_strong_boards` | `board_condition_display_basis` | `v_n6_board_condition_display_basis` | B-track dashboard/home summary helper |

These helpers are not part of `/api/n6/app/v2/filter/*` and were outside the filter-center closeout scope. They still belong to the B-track source boundary and should be aligned to the same official readonly view boundary.

## Decision

The cleanup should proceed to implementation.

The implementation must change only the read boundary:

```text
fetch_top_index_strategy -> v_n6_index_condition_display_basis
fetch_strong_boards      -> v_n6_board_condition_display_basis
```

UI wording, labels, response shape, ranking logic, filters, and ordering should remain unchanged unless a compile/test adjustment is required by the view column names.

## Source Boundary Rules

The dashboard/home helpers must not directly read:

- `index_condition_display_basis`
- `board_condition_display_basis`
- `stock_condition_display_basis`
- `condition_basis`
- `condition_pool`
- `minute_target_scope`
- raw K
- N4/N5 raw facts
- outbox
- local display cache physical tables:
  - `n6_stock_display_cache`
  - `n6_index_display_cache`
  - `n6_board_display_cache`
  - `n6_index_membership_display_cache`
  - `n6_board_membership_display_cache`

The helpers should only use the current N6 readonly views created by 036 and permissioned by 037.

## Required Implementation Scope

Modify:

- `src/ashare_v3/web/n6_user_app.py`

Required changes:

1. In `PostgresN6UserRepository.fetch_top_index_strategy`, replace:

   ```sql
   FROM index_condition_display_basis
   ```

   with:

   ```sql
   FROM v_n6_index_condition_display_basis
   ```

2. In `PostgresN6UserRepository.fetch_strong_boards`, replace:

   ```sql
   FROM board_condition_display_basis
   ```

   with:

   ```sql
   FROM v_n6_board_condition_display_basis
   ```

3. Preserve existing SELECT fields:

   ```text
   code/name or board_code/board_name
   display_title
   display_summary
   selected_signal_types
   selected_condition_keys where currently used
   period_transition_y/q/m/w/d
   buy_target_price
   sell_target_price
   ```

4. Preserve existing WHERE/ORDER/LIMIT semantics.

5. Do not introduce fallback reads to base tables, local cache, raw K, or N4/N5 raw facts.

## Required Tests

Modify:

- `tests/test_n6_user_app.py`

Add a source-boundary test for the two dashboard helpers:

1. Use a `RecordingCursor` with existing relations:

   ```python
   {
       "v_n6_index_condition_display_basis",
       "v_n6_board_condition_display_basis",
   }
   ```

2. Call:

   ```python
   repo.fetch_top_index_strategy()
   repo.fetch_strong_boards(3)
   ```

3. Assert SQL contains:

   ```text
   FROM v_n6_index_condition_display_basis
   FROM v_n6_board_condition_display_basis
   ```

4. Assert SQL does not contain direct base table reads:

   ```text
   FROM index_condition_display_basis
   FROM board_condition_display_basis
   FROM stock_condition_display_basis
   ```

5. Assert SQL does not contain forbidden local cache physical tables:

   ```text
   FROM n6_index_display_cache
   FROM n6_board_display_cache
   FROM n6_stock_display_cache
   ```

6. Keep the existing filter-center source-boundary test unchanged.

## Implementation Artifacts

The implementation gate should generate:

- `docs/B_TRACK_V2_DASHBOARD_SOURCE_BOUNDARY_CLEANUP_IMPLEMENTATION.md`
- `docs/B_TRACK_V2_DASHBOARD_SOURCE_BOUNDARY_CLEANUP_IMPLEMENTATION.json`

The implementation artifact must record:

- affected helpers
- source view replacement proof
- forbidden source scan
- targeted test result
- compileall result
- JSON parse result
- `git diff --check` result
- forbidden scope proof

## Acceptance Criteria

Implementation can pass only if:

1. `fetch_top_index_strategy` reads `v_n6_index_condition_display_basis`.
2. `fetch_strong_boards` reads `v_n6_board_condition_display_basis`.
3. No B-track dashboard helper directly reads `index_condition_display_basis` or `board_condition_display_basis`.
4. No new source fallback is added.
5. UI labels and response shape remain unchanged.
6. Targeted source-boundary tests pass.
7. `tests/test_n6_user_app.py` passes.
8. `python3 -m compileall scripts src tests` passes.
9. JSON artifacts parse.
10. `git diff --check` passes.

## Forbidden Scope

This cleanup must not:

- write database rows
- execute migrations
- execute local display cache sync
- rollback local display cache
- consume/update outbox
- start workers
- generate proposal/order/trade
- update position/PnL
- submit real trade
- change N3/N4/N5/N6 action flow

## Next Gate

```text
B_TRACK_V2_DASHBOARD_SOURCE_BOUNDARY_CLEANUP_IMPLEMENTATION_GATE
```

