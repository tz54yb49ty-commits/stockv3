# B Track V2 Field Visibility Policy Implementation Preflight

Gate: `B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION_CONTRACT_GATE`
Layer role: `runtime_control`
Status: `PREFLIGHT_PASS`
Date: `2026-06-07`

## Preflight Summary

```text
contract_status=CONTRACT_PASS
preflight_status=PREFLIGHT_PASS
P0/P1/P2=0/0/0
blockers=[]
ready_for_implementation_gate=true
```

This preflight validates the implementation contract shape only. It does not modify business code, write database rows, execute sync or migration, consume or update outbox, start workers, activate or rollback local display cache, generate proposal/order/trade, update position/PnL, or submit real trade.

## Input Readiness

Required upstream gates are available:

```text
B_TRACK_V2_FIELD_VISIBILITY_POLICY_REVIEW_GATE = APPROVED
N6_READONLY_VIEW_FIELD_WIDENING_POST_REVIEW_REGISTRATION_GATE = POST_REVIEW_PASS
B_TRACK_V2_SOURCE_BOUNDARY_GLOBAL_CLOSEOUT_GATE = CLOSEOUT_PASS
```

Required design artifacts:

```text
docs/B_TRACK_V2_FIELD_VISIBILITY_POLICY_DESIGN.md
docs/B_TRACK_V2_FIELD_VISIBILITY_POLICY_DESIGN.json
docs/B_TRACK_V2_FIELD_VISIBILITY_POLICY_TRACEABILITY.md
docs/B_TRACK_V2_FIELD_VISIBILITY_POLICY_TRACEABILITY.json
```

Design traceability:

```text
rule_count=46
coverage=100%
duplicate=0
missing=0
```

## Source Boundary Preflight

Allowed sources are exactly:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
v_n6_index_membership_fact
v_n6_board_membership_fact
```

The contract preserves logical source labels:

```text
n6_display_stock_condition_cache
n6_display_index_condition_cache
n6_display_board_condition_cache
n6_display_index_membership_cache
n6_display_board_membership_cache
```

Forbidden source checks required for the implementation gate:

```text
base display/membership table reads = must be 0
experimental local display cache reads = must be 0
condition_basis / condition_pool / minute_target_scope reads = must be 0
raw K / direct live market reads = must be 0
N4/N5 raw facts bypass = must be 0
unreviewed outbox reads = must be 0
```

## Endpoint Allowlist Preflight

Endpoint contracts defined:

| Endpoint | Source relation | Default mode |
|---|---|---|
| `/api/n6/app/v2/filter/stocks` | `v_n6_stock_condition_display_basis` | compact explicit allowlist |
| `/api/n6/app/v2/filter/indexes` | `v_n6_index_condition_display_basis` | compact explicit allowlist |
| `/api/n6/app/v2/filter/boards` | `v_n6_board_condition_display_basis` | compact explicit allowlist |
| `/api/n6/app/v2/filter/board-members` | `v_n6_board_membership_fact` | compact explicit allowlist |
| `/api/n6/app/v2/filter/index-members` | `v_n6_index_membership_fact` | compact explicit allowlist |

Default response rules:

```text
GET-only=true
principal_scoped=true
SELECT_STAR_to_frontend=false
default_response_field_allowlist_required=true
raw_payload_default_visible=false
include_detail_authorized=false
include_audit_authorized=false
```

Forbidden default fields:

```text
period_trigger_baseline_json
raw_json
raw_payload
target_price_trace_json
score_breakdown_json
financial_warning_json
source_condition_basis_ids_json
source_condition_pool_ids_json
source_minute_target_scope_ids_json
source_row_count_json
up_secondary_expected_return_pct
down_secondary_expected_return_pct
target_price_trace_json_raw_body
period_trigger_baseline_json_raw_body
financial_warning_json_raw_body
```

## Implementation Scope Preflight

Expected implementation files:

```text
src/ashare_v3/web/n6_user_app.py
src/ashare_v3/web/n6_app_v1.py
tests/test_n6_user_app.py
docs/B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION.md
docs/B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION.json
```

Allowed implementation scope:

```text
B-track V2 filter repository selectors
B-track V2 filter response adapters
B-track V2 filter-center page rendering
B-track V2 filter tests
implementation proof artifacts
```

Forbidden implementation scope:

```text
A-track /api/n6/ui/v1 routes
N3/N4/N5/N6 action/projection/card pipelines
database schema / migrations
local display cache sync/activation/rollback
outbox/inbox/checkpoint mutation
proposal/order/trade
position/PnL
real trade
worker
```

## Required Implementation Tests

The next implementation gate must prove:

```text
v2 filter routes GET-only
default response field allowlist exact match
forbidden default fields absent
membership default response excludes raw_payload
no SELECT * for frontend payloads
no base display/membership table reads
no experimental local display cache reads
no raw K / N4/N5 raw facts / unreviewed outbox reads
include=detail and include=audit do not expand fields in this gate
forbidden wording absent from filter-center UI/API output
source_table remains logical n6_display_*_cache label
principal scope remains enforced
```

## Forbidden Wording Preflight

Implementation must keep these user-facing terms absent:

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

## Forbidden Scope Proof

```text
business_code_modified_by_this_gate=false
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
PREFLIGHT_PASS
ready_for_implementation_gate=true
next_gate=B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION_GATE
```
