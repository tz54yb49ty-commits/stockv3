# B Track V2 Field Visibility Policy Design

Gate: `B_TRACK_V2_FIELD_VISIBILITY_POLICY_DESIGN_GATE`  
Layer role: `runtime_control`  
Status: `DESIGN_PASS`  
Date: `2026-06-07`

## Goal

Define how B-track V2 should expose the newly widened N6 readonly view fields without dumping every N2 source field into the user UI. The policy keeps B-track source authority on `v_n6_*` readonly views, keeps current list pages compact, and reserves trace-heavy fields for later detail/audit surfaces.

This is a design artifact only. It does not change code, write database rows, execute migration, consume outbox, start workers, or alter proposal/order/trade/position/PnL behavior.

## Source Boundary

Official B-track display sources remain:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
v_n6_index_membership_fact
v_n6_board_membership_fact
```

UI/API logical source labels may continue to show:

```text
n6_display_stock_condition_cache
n6_display_index_condition_cache
n6_display_board_condition_cache
n6_display_index_membership_cache
n6_display_board_membership_cache
```

Forbidden sources remain:

```text
stock/index/board_condition_display_basis base tables
n6_*_display_cache physical tables
condition_basis
condition_pool
minute_target_scope
raw K
direct live market
N4/N5 raw facts bypass
unreviewed outbox
```

## Field Visibility Tiers

### Default List Fields

Default list responses and list UI should remain compact and scan-oriented.

Common default fields:

```text
asset_kind
source_display_basis_id
run_id
for_trade_date
source_trade_date
identity_key
display_code
display_name
display_title
display_summary
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
buy_target_price
sell_target_price
up_sell_reference_period
down_buy_reference_period
quality_status
quality_reason
display_status
source_table
```

Stock-only default fields:

```text
code
exchange
name
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
```

Index-only default fields:

```text
code
exchange
name
fixed_index_member
```

Board-only default fields:

```text
board_code
board_name
board_type
is_industry_board
```

Membership default fields:

```text
trade_date
index_identity_key / board_identity_key
stock_identity_key
index_code / board_code
index_name / board_name
board_type
stock_code
stock_name
source_table
```

### Detail Fields

Detail drawer/page fields can explain why a row appears in the filter center, but should still avoid raw trace dumps.

Detail fields:

```text
condition_summary_json
target_price_summary_json
reference_period_summary_json
period_grade_summary_json
period_transition_summary_json
prev_up_str
prev_dn_str
period_trigger_baseline_json summary only
display_policy_name
display_policy_hash
condition_pool_policy_name
condition_pool_policy_hash
scope_policy_name
scope_policy_hash
display_scope_reason
selected_reason
excluded_reason
missing_fields_json
official_daily_proof
financial_quality_status
pe_core
cash_realization_rate
revenue_yoy_pct
core_profit_yoy_pct
report_core_revenue
report_core_profit
core_profit_ttm
forecast_type
forecast_score
level_up_score
level_down_score
```

Target and score wording must remain descriptive and factual. It must not imply an instruction to buy, sell, trade, or expect future returns.

### Audit Fields

Audit fields are for trace/debug panels and operator-reviewed evidence. They may be API-available only through an explicit allowlist in a future implementation gate.

Audit fields:

```text
stock/index/board_condition_display_basis_id
primary_source_condition_basis_id
primary_source_condition_pool_id
primary_source_minute_target_scope_id
source_condition_basis_ids_json
source_condition_pool_ids_json
source_minute_target_scope_ids_json
source_row_count_json
source_version
raw_json
symmetry_anchor
secondary_symmetry_anchor
amplitude_source_period
a_segment_start_date
a_segment_end_date
a_segment_high
a_segment_low
a_segment_amplitude
base_price_policy
base_price
reference_target_price
secondary_target_price
target_price_trace_json
up_secondary_anchor
up_secondary_reference_period
up_secondary_trend_start_date
up_secondary_trend_end_date
up_secondary_amplitude
up_secondary_base_price
up_secondary_target_price
up_secondary_expected_return_pct
down_secondary_anchor
down_secondary_reference_period
down_secondary_trend_start_date
down_secondary_trend_end_date
down_secondary_amplitude
down_secondary_base_price
down_secondary_target_price
down_secondary_expected_return_pct
score_breakdown_json
financial_warning_json
financial_metric_version
membership raw_payload
created_at
updated_at
```

### Hidden-By-Default Fields

Hidden-by-default fields are not shown in list UI and should not appear in default API payloads. They may be exposed only through explicit field allowlists:

```text
period_trigger_baseline_json
raw_json
target_price_trace_json
score_breakdown_json
financial_warning_json
membership raw_payload
source_*_ids_json
source_row_count_json
secondary anchor expected return fields
```

### Internal-Only Fields

Internal-only fields should not be displayed to normal B-track users. They are for support/debugging, future gate validation, or trace reconstruction:

```text
raw_json
membership raw_payload
source_condition_basis_ids_json
source_condition_pool_ids_json
source_minute_target_scope_ids_json
target_price_trace_json raw body
period_trigger_baseline_json raw body
financial_warning_json raw body
```

Future implementation can present summarized versions of some internal fields, but direct raw JSON passthrough requires a dedicated audit UI gate.

## Page Scope

### `/n6/app/filter-center`

Default behavior:

```text
use default list fields
keep source_table logical label as n6_display_*_cache
do not show raw trace JSON
do not show every widened column
```

Future detail behavior:

```text
detail drawer may request detail fields
audit panel may request audit fields after separate gate
```

### Dashboard / Home Helper

Dashboard and home helpers should stay summary-oriented:

```text
use display code/name/title/summary
use selected directions and condition keys
use quality/status and period grades
do not add trace-heavy fields by default
```

### Future Detail Drawer

Future detail drawer is the natural home for:

```text
period summaries
target summaries
financial/risk summary
policy trace
source lineage summary
```

Audit raw JSON remains behind a separate audit panel or operator mode.

### Membership Lookup

Membership lookup should return relational membership fields by default. `raw_payload` is hidden by default and belongs to audit mode.

### Signals / Status / Watchlist

This gate does not change signals, status-monitor, or watchlist behavior. Those surfaces continue using reviewed N6 projection/card sources under their existing source-boundary rules.

## API Policy

Default v2 filter API responses must remain compact. They should not emit all widened columns and must not use `SELECT *` for frontend payloads.

Required API rules:

```text
default response = explicit field allowlist only
source query may read from v_n6_* readonly views only
frontend payload must not mirror every database column
no base table reads
no local display cache reads
no raw K / N4/N5 raw bypass / unreviewed outbox
```

Future optional include modes:

```text
include=detail -> explicit detail field allowlist
include=audit -> explicit audit field allowlist, operator/audit gate required
```

`include=detail` and `include=audit` are design placeholders only. They are not authorized for implementation by this gate.

## Safety Wording Policy

Financial, target, score, and structure fields must be factual, not advisory. UI copy should use neutral words such as:

```text
观察方向
条件来源
结构分
目标价候选
来源追踪
质量状态
财务摘要
```

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

Target price and expected-return fields must be framed as N2 trace/evidence fields, not future return promises.

## Forbidden Scope Proof

```text
code_modified=false
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

## Next Gate

Allowed next gate:

```text
B_TRACK_V2_FIELD_VISIBILITY_POLICY_REVIEW_GATE
```
