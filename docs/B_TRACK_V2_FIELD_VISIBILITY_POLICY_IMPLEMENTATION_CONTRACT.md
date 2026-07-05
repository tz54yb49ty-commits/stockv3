# B Track V2 Field Visibility Policy Implementation Contract

Gate: `B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION_CONTRACT_GATE`
Layer role: `runtime_control`
Status: `CONTRACT_PASS`
Date: `2026-06-07`

## Goal

Define the implementation contract for B-track V2 filter field visibility after N6 readonly view widening. The contract keeps B-track source authority on readonly views, keeps default API/UI payloads compact, and prevents widened N2 trace fields from being exposed by accident.

This gate writes only contract and preflight artifacts. It does not modify business code, write database rows, execute sync or migration, consume or update outbox, start workers, activate local display cache, create proposal/order/trade, update position/PnL, or submit real trade.

## Basis

Reviewed inputs:

```text
B_TRACK_V2_FIELD_VISIBILITY_POLICY_REVIEW_GATE = APPROVED
N6_READONLY_VIEW_FIELD_WIDENING_POST_REVIEW_REGISTRATION_GATE = POST_REVIEW_PASS
B_TRACK_V2_SOURCE_BOUNDARY_GLOBAL_CLOSEOUT_GATE = CLOSEOUT_PASS
```

View widening proof:

```text
v_n6_stock_condition_display_basis = 131 columns
v_n6_index_condition_display_basis = 100 columns
v_n6_board_condition_display_basis = 100 columns
v_n6_index_membership_fact = 13 columns
v_n6_board_membership_fact = 14 columns
```

## Source Boundary Contract

Allowed B-track V2 filter sources:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
v_n6_index_membership_fact
v_n6_board_membership_fact
```

Allowed UI/API logical source labels:

```text
n6_display_stock_condition_cache
n6_display_index_condition_cache
n6_display_board_condition_cache
n6_display_index_membership_cache
n6_display_board_membership_cache
```

Forbidden sources:

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
direct live market
N4/N5 raw facts bypass
unreviewed outbox
```

The implementation must not fan out rows, rewrite N2 semantics, or change asset row grain. It may only select an explicit subset of fields from the approved readonly views.

## Endpoint Default Field Allowlist

All endpoints remain GET-only and principal-scoped. Default payload mode is:

```text
compact_explicit_allowlist
```

The implementation must not use `SELECT *` for frontend payloads.

### Shared Envelope Fields

Every V2 filter endpoint may return only the following envelope fields by default:

```text
ok
component
component_label
principal
status
status_label
empty_state
filters
items
controls
readonly
safety_banner
source_policy
side_effects
```

Membership endpoints may additionally return:

```text
membership_kind
parent_identity_key
source_table
```

### `/api/n6/app/v2/filter/stocks`

Method: `GET`
Source relation: `v_n6_stock_condition_display_basis`
Logical source label: `n6_display_stock_condition_cache`

Default item allowlist:

```text
asset_kind
asset_kind_label
source_display_basis_id
run_id
source_run_id
for_trade_date
source_trade_date
identity_key
stock_identity_key
code
exchange
name
display_code
display_name
display_title
display_summary
direction
direction_label
condition_key
selected_directions
selected_condition_keys
selected_signal_types
selected_lanes
selected_monitor_types
period_grade_y
period_grade_q
period_grade_m
period_grade_w
period_grade_d
period_transition_y
period_transition_q
period_transition_m
period_transition_w
period_transition_d
year_overheat_level
quarter_overheat_level
month_overheat_level
week_overheat_level
day_overheat_level
buy_target_price
sell_target_price
up_sell_reference_period
down_buy_reference_period
total_mv
circ_mv
score
recommendation_level
main_index_code
main_index_name
preferred_board_code
preferred_board_name
is_st
stock_status
quality_status
quality_reason
display_status
last_signal_state
last_signal_state_label
projection_run_id
cache_run_id
source_table
readonly
add_monitor_enabled
add_monitor_label
investment_advice
```

### `/api/n6/app/v2/filter/indexes`

Method: `GET`
Source relation: `v_n6_index_condition_display_basis`
Logical source label: `n6_display_index_condition_cache`

Default item allowlist:

```text
asset_kind
asset_kind_label
source_display_basis_id
run_id
source_run_id
for_trade_date
source_trade_date
identity_key
index_identity_key
code
exchange
name
display_code
display_name
display_title
display_summary
direction
direction_label
condition_key
selected_directions
selected_condition_keys
selected_signal_types
selected_lanes
selected_monitor_types
period_grade_y
period_grade_q
period_grade_m
period_grade_w
period_grade_d
period_transition_y
period_transition_q
period_transition_m
period_transition_w
period_transition_d
year_overheat_level
quarter_overheat_level
month_overheat_level
week_overheat_level
day_overheat_level
buy_target_price
sell_target_price
up_sell_reference_period
down_buy_reference_period
fixed_index_member
quality_status
quality_reason
display_status
last_signal_state
last_signal_state_label
projection_run_id
cache_run_id
source_table
readonly
add_monitor_enabled
add_monitor_label
investment_advice
```

### `/api/n6/app/v2/filter/boards`

Method: `GET`
Source relation: `v_n6_board_condition_display_basis`
Logical source label: `n6_display_board_condition_cache`

Default item allowlist:

```text
asset_kind
asset_kind_label
source_display_basis_id
run_id
source_run_id
for_trade_date
source_trade_date
identity_key
board_identity_key
board_code
board_name
board_type
display_code
display_name
display_title
display_summary
direction
direction_label
condition_key
selected_directions
selected_condition_keys
selected_signal_types
selected_lanes
selected_monitor_types
period_grade_y
period_grade_q
period_grade_m
period_grade_w
period_grade_d
period_transition_y
period_transition_q
period_transition_m
period_transition_w
period_transition_d
year_overheat_level
quarter_overheat_level
month_overheat_level
week_overheat_level
day_overheat_level
buy_target_price
sell_target_price
up_sell_reference_period
down_buy_reference_period
is_industry_board
quality_status
quality_reason
display_status
last_signal_state
last_signal_state_label
projection_run_id
cache_run_id
source_table
readonly
add_monitor_enabled
add_monitor_label
investment_advice
```

### `/api/n6/app/v2/filter/board-members`

Method: `GET`
Source relation: `v_n6_board_membership_fact`
Logical source label: `n6_display_board_membership_cache`

Default item allowlist:

```text
membership_kind
trade_date
parent_identity_key
board_identity_key
parent_code
board_code
parent_name
board_name
board_type
stock_identity_key
stock_code
stock_name
source_version
source_batch_id
source_table
readonly
```

### `/api/n6/app/v2/filter/index-members`

Method: `GET`
Source relation: `v_n6_index_membership_fact`
Logical source label: `n6_display_index_membership_cache`

Default item allowlist:

```text
membership_kind
trade_date
parent_identity_key
index_identity_key
parent_code
index_code
parent_name
index_name
stock_identity_key
stock_code
stock_name
source_version
source_batch_id
source_table
readonly
```

## Forbidden Default Fields

The following fields must not appear in default endpoint responses:

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

Membership lookup must not return `raw_payload` by default.

## Future Include Policy

`include=detail` and `include=audit` are not authorized by this contract.

Implementation rules:

```text
include=detail must not expand response fields in this gate
include=audit must not expand response fields in this gate
if include handling already exists, it must remain no-op or the implementation gate must BLOCK
detail drawer requires a separate implementation gate
audit/raw JSON panel requires a separate operator/audit gate
```

## UI Behavior Contract

`/n6/app/filter-center` default behavior:

```text
show default list fields only
keep logical source labels
do not show raw trace JSON
do not show every widened column
do not introduce proposal/order/trade buttons
do not introduce position/PnL/real performance widgets
```

Dashboard/home helper behavior remains summary-oriented and is not expanded by this gate.

Signals, status-monitor, and watchlist are not modified by this gate.

## Safety Wording Contract

Financial, target, score, and structure fields must remain factual evidence labels. They must not be phrased as advice, execution, real account, real return, or performance promise.

Forbidden user-facing wording:

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

Allowed neutral wording examples:

```text
观察方向
条件来源
结构分
目标价候选
来源追踪
质量状态
财务摘要
```

## Required Tests For Implementation Gate

The implementation gate must add or preserve tests covering:

```text
v2 filter routes are GET-only
default response field allowlist exact match
forbidden default fields absent
membership default response excludes raw_payload
no SELECT * for frontend payloads
no base display/membership table reads
no experimental local display cache reads
no raw K / N4/N5 raw facts / unreviewed outbox reads
include=detail and include=audit do not expand fields in this gate
forbidden wording absent from user-facing filter-center UI/API output
source_table remains logical n6_display_*_cache label
principal scope remains enforced
```

Expected implementation files:

```text
src/ashare_v3/web/n6_user_app.py
src/ashare_v3/web/n6_app_v1.py
tests/test_n6_user_app.py
docs/B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION.md
docs/B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION.json
```

Allowed code scope:

```text
B-track V2 filter repository selectors
B-track V2 filter response adapters
B-track V2 filter-center page rendering
B-track V2 filter tests
implementation proof artifacts
```

Forbidden code scope:

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

## Contract Decision

```text
CONTRACT_PASS
blockers=[]
ready_for_implementation_gate=true
next_gate=B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION_GATE
```
