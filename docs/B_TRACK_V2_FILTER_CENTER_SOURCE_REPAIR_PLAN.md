# B Track V2 Filter Center Source Repair Plan

Gate: `B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_PLAN_GATE`  
Layer role: `runtime_control`  
Result: `REPAIR_PLAN_PASS`  
Date: `2026-06-07`

This plan is documentation-only. It does not modify code, write database rows, consume/update outbox, start workers, generate proposal/order/trade, update position/PnL, or submit real trade.

## Problem Statement

B Track V2 filter center currently mixes three source naming layers:

| Layer | Purpose | Current names |
|---|---|---|
| Current N6 read-only DB views | Official B-track/N6 read boundary | `v_n6_stock_condition_display_basis`, `v_n6_index_condition_display_basis`, `v_n6_board_condition_display_basis`, `v_n6_index_membership_fact`, `v_n6_board_membership_fact` |
| B-track display source labels | UI/API evidence labels only | `n6_display_stock_condition_cache`, `n6_display_index_condition_cache`, `n6_display_board_condition_cache`, `n6_display_index_membership_cache`, `n6_display_board_membership_cache` |
| Future/experimental local cache physical tables | Optional later cache layer, not current official source | `n6_stock_display_cache`, `n6_index_display_cache`, `n6_board_display_cache`, `n6_index_membership_display_cache`, `n6_board_membership_display_cache` |

The implementation and recent post-review incorrectly treated the third layer as the official B-track source. That is wrong for current B-track V2 filter center.

## Evidence

The user-provided Excel file:

```text
/Users/chuanfuchen/Desktop/N2_condition_display_basis_20260604_active.xlsx
```

contains the official N2 display input for N6:

| Sheet | Source rows |
|---|---:|
| `个股展示明细` | 1,952 |
| `指数展示明细` | 9 |
| `板块展示明细` | 428 |

The live N2 DB source rows match the Excel source rows:

```text
stock_condition_display_basis = 1952
index_condition_display_basis = 9
board_condition_display_basis = 428
index_membership_fact = 12841
board_membership_fact = 56960
```

The current active local display cache is not semantically aligned:

| Asset | Source rows | Correct condition-key rows | Current local cache rows | Over-expanded rows |
|---|---:|---:|---:|---:|
| stock | 1,952 | 4,186 | 8,370 | 4,184 |
| index | 9 | 20 | 40 | 20 |
| board | 428 | 912 | 1,824 | 912 |
| total display | 2,389 | 5,118 | 10,234 | 5,116 |

Root causes:

1. `cartesian_fanout_v1` expands `selected_directions x selected_condition_keys`, producing invalid combinations such as `buy + SELL:*` and `sell + BUY:*`.
2. B-track filter reads period levels from `period_summary_json->>'year_overheat_level'`, but the source JSON keys are `Y/Q/M/W/D`. The correct period fields already exist as direct columns: `period_grade_y/q/m/w/d` in the N6 views and `year_overheat_level/quarter...` in the experimental cache.
3. B-track filter currently reads the future physical cache tables instead of the official `v_n6_*` read-only views.

## Decision

`B_TRACK_V2_FILTER_CENTER_CLOSEOUT_GATE` must remain blocked.

The prior `B_TRACK_V2_FILTER_CENTER_POST_REVIEW` result is superseded by this source repair plan for the filter-center source boundary. It only proved that a local cache exists and returns rows; it did not prove N2-to-N6 semantic alignment.

## Repair Target

B Track V2 filter center must read the current official N6 read-only views:

| API / UI use | Official source view | Display source label |
|---|---|---|
| stock filter | `v_n6_stock_condition_display_basis` | `n6_display_stock_condition_cache` |
| index filter | `v_n6_index_condition_display_basis` | `n6_display_index_condition_cache` |
| board filter | `v_n6_board_condition_display_basis` | `n6_display_board_condition_cache` |
| index members | `v_n6_index_membership_fact` | `n6_display_index_membership_cache` |
| board members | `v_n6_board_membership_fact` | `n6_display_board_membership_cache` |

The filter center must show N2-provided display_basis fields without local fanout or semantic rewriting. Field hiding, UI grouping, and presentation simplification are future UI gates.

## Required Implementation Scope

The next implementation gate must:

1. Change B-track filter repository reads from `n6_*_display_cache` physical tables to `v_n6_*` views.
2. Preserve N2 display row granularity:
   - stock rows = 1,952
   - index rows = 9
   - board rows = 428
3. Preserve arrays as arrays:
   - `selected_directions`
   - `selected_condition_keys`
   - `selected_signal_types`
   - `selected_lanes`
   - `selected_monitor_types`
4. Read period fields from direct view columns:
   - `period_grade_y`
   - `period_grade_q`
   - `period_grade_m`
   - `period_grade_w`
   - `period_grade_d`
5. Use B-track display labels only as labels, not physical table names.
6. Keep membership reads on `v_n6_index_membership_fact` and `v_n6_board_membership_fact`.
7. Keep all APIs read-only GET-only and principal-scoped.

## Explicit Non-Goals

This repair must not:

- add new database schema
- write DB rows
- execute sync
- consume/update outbox
- start worker
- read `condition_basis`
- read `condition_pool`
- read `minute_target_scope`
- read raw K
- read N4/N5 raw facts
- generate proposal/order/trade
- update position/PnL
- submit real trade
- decide final UI field hiding

## Local Display Cache Status

The current active local display cache run:

```text
cache_run_id=n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1
cache_version=n6_display_cache_v1
```

must be treated as `experimental/tainted_for_b_track_filter_center`.

Recommended handling:

```text
Do not use it for B-track filter center.
Do not rollback it from this repair gate.
If DB cleanup is desired, open a separate N6_LOCAL_DISPLAY_CACHE_SEMANTIC_TAINTED_ROLLBACK_FINAL_GATE.
```

## Acceptance Criteria

The implementation post-review must prove:

1. `/api/n6/app/v2/filter/stocks` reads `v_n6_stock_condition_display_basis`.
2. `/api/n6/app/v2/filter/indexes` reads `v_n6_index_condition_display_basis`.
3. `/api/n6/app/v2/filter/boards` reads `v_n6_board_condition_display_basis`.
4. `/api/n6/app/v2/filter/index-members` reads `v_n6_index_membership_fact`.
5. `/api/n6/app/v2/filter/board-members` reads `v_n6_board_membership_fact`.
6. B-track API response no longer uses `n6_stock_display_cache`, `n6_index_display_cache`, or `n6_board_display_cache` as physical sources.
7. Response source labels remain the B-track logical names:
   - `n6_display_stock_condition_cache`
   - `n6_display_index_condition_cache`
   - `n6_display_board_condition_cache`
   - `n6_display_index_membership_cache`
   - `n6_display_board_membership_cache`
8. Source row counts match N2:
   - stock = 1,952
   - index = 9
   - board = 428
   - index membership = 12,841
   - board membership = 56,960
9. No invalid direction/condition combinations are generated because no fanout is performed.
10. Period filters use direct period columns, not nonexistent JSON keys.
11. Forbidden source scan passes.
12. Targeted tests pass.
13. `git diff --check` passes.

## Required Artifacts For Next Gates

Implementation gate should generate:

- `docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION.md`
- `docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION.json`

Post-review gate should generate:

- `docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_POST_REVIEW.md`
- `docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_POST_REVIEW.json`

## Recommended Next Gate

```text
B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_PLAN_REVIEW_GATE
```

If approved, proceed to:

```text
B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION_GATE
```

## Runtime Control Review Prompt

```text
layer_role=runtime_control。

进入 B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_PLAN_REVIEW_GATE。

目标：
只读审核 B轨 V2 筛选中心 source repair plan 是否允许进入 implementation gate。

依据：
- docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_PLAN.md
- docs/B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_PLAN.json
- /Users/chuanfuchen/Desktop/N2_condition_display_basis_20260604_active.xlsx
- sql/036_n6_multi_user_ai_owner_principal_schema.sql
- sql/037_n6_view_readonly_permission.sql

背景：
当前存在三层来源名，之前 B轨筛选中心误把未来本地 cache 物理表 n6_*_display_cache 当成正式来源。
当前正式 N6 只读来源应为 v_n6_* views。
B轨页面/API 展示的 n6_display_*_cache 只是逻辑 source label。

已发现：
- N2 Excel/DB source rows stock/index/board=1952/9/428
- 正确 condition-key 粒度 rows stock/index/board=4186/20/912
- 当前 local cache rows stock/index/board=8370/40/1824
- 多出 5116 行 invalid direction/condition cartesian pair
- B轨 filter 周期字段读取 period_summary_json->year_overheat_level 等不存在 key

要求：
- 只读
- 不改代码
- 不写数据库
- 不 execute
- 不消费/update outbox
- 不启动 worker
- 不生成 proposal/order/trade
- 不更新 position/PnL
- 不提交 real trade

请审核：
1. 三层来源名定义是否正确。
2. 是否应 BLOCK B_TRACK_V2_FILTER_CENTER_CLOSEOUT_GATE。
3. 是否应将当前 local display cache 标记为 experimental/tainted_for_b_track_filter_center。
4. B轨筛选中心是否应切回读取 v_n6_* views。
5. 是否应保持 B轨 source label 为 n6_display_*_cache。
6. 是否禁止 fanout / 二次加工 / semantic rewrite。
7. 是否应原样展示 N2 display_basis 字段，字段隐藏后续单独 gate。
8. 是否需要单独 local cache rollback final gate，或仅停止使用。
9. 是否允许进入 B_TRACK_V2_FILTER_CENTER_SOURCE_REPAIR_IMPLEMENTATION_GATE。

输出：
- APPROVED / APPROVED_WITH_CHANGES / BLOCKED
- 必须修改项
- 建议修改项
- 是否允许进入 implementation gate
```
