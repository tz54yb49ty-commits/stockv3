# N6 Readonly View Field Widening Field Mapping

Gate: `N6_READONLY_VIEW_FIELD_WIDENING_DRAFT_GATE`  
Layer role: `runtime_control`  
Status: draft mapping only; no migration executed.

## Source Inventory

| Source | Current readonly view | Current view columns | Source columns | Draft widened columns | Coverage note |
|---|---|---:|---:|---:|---|
| `stock_condition_display_basis` | `v_n6_stock_condition_display_basis` | 68 | 128 | 131 | Covers all source columns; keeps normalized `asset_kind`, `source_display_basis_id`, `identity_key` aliases and also appends raw source id. |
| `index_condition_display_basis` | `v_n6_index_condition_display_basis` | 57 | 97 | 100 | Covers all source columns; keeps normalized aliases and appends raw source id. |
| `board_condition_display_basis` | `v_n6_board_condition_display_basis` | 57 | 97 | 100 | Covers all source columns; keeps board type allowlist. |
| `index_membership_fact` | `v_n6_index_membership_fact` | 12 | 13 | 13 | Adds only missing source field `raw_payload`. |
| `board_membership_fact` | `v_n6_board_membership_fact` | 13 | 14 | 14 | Adds only missing source field `raw_payload`; keeps board type allowlist. |

## Existing Compatibility Columns

The draft preserves all existing view columns and their order. Existing B-track API readers can keep using:

```text
asset_kind
source_display_basis_id
run_id
for_trade_date
source_trade_date
prev_trade_date
identity_key
display_code / display_name / display_title / display_summary
selected_directions / selected_condition_keys / selected_signal_types
period_grade_y/q/m/w/d
period_transition_y/q/m/w/d
buy_target_price / sell_target_price
display_policy_* / condition_pool_policy_* / scope_policy_*
display_status / quality_status / quality_reason
```

No existing column is renamed, removed, reordered, or semantically rewritten.

## Stock Added Fields

`v_n6_stock_condition_display_basis` appends:

```text
stock_condition_display_basis_id
prev_up_str
prev_dn_str
period_trigger_baseline_json
pe_core
is_st
stock_status
official_daily_proof
financial_quality_status
cash_realization_rate
revenue_yoy_pct
core_profit_yoy_pct
report_core_revenue
report_core_profit
core_profit_ttm
core_gt_revenue_yoy
revenue_growth_streak_q
core_growth_streak_q
core_gt_revenue_streak_q
forecast_type
forecast_score
score_breakdown_json
financial_warning_json
financial_metric_version
primary_source_condition_basis_id
primary_source_condition_pool_id
primary_source_minute_target_scope_id
source_condition_basis_ids_json
source_condition_pool_ids_json
source_minute_target_scope_ids_json
source_row_count_json
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
level_up_score
level_down_score
```

## Index Added Fields

`v_n6_index_condition_display_basis` appends:

```text
index_condition_display_basis_id
prev_up_str
prev_dn_str
period_trigger_baseline_json
primary_source_condition_basis_id
primary_source_condition_pool_id
primary_source_minute_target_scope_id
source_condition_basis_ids_json
source_condition_pool_ids_json
source_minute_target_scope_ids_json
source_row_count_json
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
level_up_score
level_down_score
```

## Board Added Fields

`v_n6_board_condition_display_basis` appends the same non-stock widening set as index:

```text
board_condition_display_basis_id
prev_up_str
prev_dn_str
period_trigger_baseline_json
primary_source_condition_basis_id
primary_source_condition_pool_id
primary_source_minute_target_scope_id
source_condition_basis_ids_json
source_condition_pool_ids_json
source_minute_target_scope_ids_json
source_row_count_json
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
level_up_score
level_down_score
```

## Membership Mapping

Current membership views already expose all relational membership fields used by B-track. The only base source field not exposed is `raw_payload`, which is useful for audit/detail inspection and does not alter row grain.

```text
v_n6_index_membership_fact: add raw_payload
v_n6_board_membership_fact: add raw_payload
```

## Boundary

This mapping does not authorize B-track to read base tables directly. Official N6/B-track sources remain:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
v_n6_index_membership_fact
v_n6_board_membership_fact
```

The UI/API logical label can remain `n6_display_*_cache`. The experimental local display cache physical tables remain out of scope and tainted for B-track filter-center until a separate gate changes that status.
