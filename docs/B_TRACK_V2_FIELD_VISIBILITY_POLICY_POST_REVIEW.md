# B Track V2 Field Visibility Policy Post Review

Gate: `B_TRACK_V2_FIELD_VISIBILITY_POLICY_POST_REVIEW_GATE`
Layer role: `runtime_control`
Status: `POST_REVIEW_PASS`
Date: `2026-06-07`

## Proof Summary

B-track V2 filter-center/API now uses compact explicit allowlists for default responses while keeping source reads on the approved readonly views.

The implementation preserves:

```text
source authority = v_n6_* readonly views
UI/API source labels = n6_display_*_cache
GET-only V2 filter routes
principal scoped reads
no detail/audit expansion by default
```

## Endpoint Proof

Reviewed endpoints:

```text
/api/n6/app/v2/filter/stocks
/api/n6/app/v2/filter/indexes
/api/n6/app/v2/filter/boards
/api/n6/app/v2/filter/board-members
/api/n6/app/v2/filter/index-members
```

Default item key sets are contract-driven and exact-match tested against:

```text
docs/B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION_CONTRACT.json
```

## Forbidden Default Fields Proof

Default responses exclude:

```text
raw_json
raw_payload
period_trigger_baseline_json
target_price_trace_json
score_breakdown_json
financial_warning_json
source_condition_basis_ids_json
source_condition_pool_ids_json
source_minute_target_scope_ids_json
source_row_count_json
secondary expected-return fields
```

Membership endpoints exclude `raw_payload` by default.

## Source Boundary Proof

No B-track V2 filter implementation path reads:

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
index_membership_fact
board_membership_fact
n6_stock_display_cache
n6_index_display_cache
n6_board_display_cache
n6_index_membership_display_cache
n6_board_membership_display_cache
condition_basis
condition_pool
minute_target_scope
raw K
N4/N5 raw facts bypass
unreviewed outbox
```

## UI Wording Proof

Filter-center remains readonly and non-advisory:

```text
readonly=true
investment_advice=false
add_monitor_enabled=false
write_route_registered=false
write_route_enabled=false
```

Forbidden wording remains absent from filter-center UI/API output:

```text
建议买入
建议卖出
买入机会
卖出提醒
一键下单
已买入
已卖出
已成交
实盘账户
可用下单资金
真实收益
稳赚
高胜率
低风险
高收益
```

## Validation Summary

Executed validation:

```text
PYTHONPATH=src python3 -m unittest tests.test_n6_user_app
```

Result:

```text
80 tests OK
```

Additional validation is recorded in closeout after final static scans.

## Forbidden Scope Proof

```text
database_written=false
execute_performed=false
outbox_consumed_or_updated=false
worker_started=false
local_display_cache_synced=false
local_display_cache_activated=false
local_display_cache_rollback=false
proposal_generated=false
order_generated=false
trade_generated=false
position_updated=false
pnl_updated=false
real_trade_submitted=false
action_flow_mutated=false
```

## Decision

```text
POST_REVIEW_PASS
next_gate=B_TRACK_V2_FIELD_VISIBILITY_POLICY_CLOSEOUT_GATE
```
