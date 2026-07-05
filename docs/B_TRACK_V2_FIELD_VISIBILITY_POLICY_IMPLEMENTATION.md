# B Track V2 Field Visibility Policy Implementation

Gate: `B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION_GATE`
Layer role: `runtime_control`
Status: `IMPLEMENTATION_PASS`
Date: `2026-06-07`

## Goal

Implement the approved B-track V2 field visibility policy so default filter-center API payloads are compact, explicit, and safe after N6 readonly views were widened.

This implementation does not write database rows, execute migrations or sync, consume/update outbox, start workers, sync/activate/rollback local display cache, generate proposal/order/trade, update position/PnL, submit real trade, or mutate N3/N4/N5/N6 action flow.

## Changed Files

```text
src/ashare_v3/web/n6_user_app.py
src/ashare_v3/web/n6_app_v1.py
tests/test_n6_user_app.py
docs/B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION.md
docs/B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION.json
```

## Implementation Summary

Repository selectors now keep B-track V2 filter reads on the official readonly views:

```text
stocks -> v_n6_stock_condition_display_basis
indexes -> v_n6_index_condition_display_basis
boards -> v_n6_board_condition_display_basis
index-members -> v_n6_index_membership_fact
board-members -> v_n6_board_membership_fact
```

Response adapters now emit asset-specific compact allowlists:

```text
stock filter rows contain stock fields only
index filter rows contain index fields only
board filter rows contain board fields only
membership rows contain their membership-kind fields only
```

The implementation removes cross-asset placeholder fields from default item payloads and adds the approved list fields from the contract.

## Endpoint Allowlist Proof

Default compact allowlists are enforced for:

```text
/api/n6/app/v2/filter/stocks
/api/n6/app/v2/filter/indexes
/api/n6/app/v2/filter/boards
/api/n6/app/v2/filter/board-members
/api/n6/app/v2/filter/index-members
```

Each endpoint remains:

```text
method=GET
principal_scoped=true
default_response_mode=compact_explicit_allowlist
source_table_label=n6_display_*_cache
```

## Forbidden Default Fields Proof

The default adapters do not expose:

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

`include=detail` and `include=audit` are not implemented as expansion modes by this gate. Supplying those query params does not expand default fields.

## Source Boundary Proof

Allowed B-track filter sources remain:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
v_n6_index_membership_fact
v_n6_board_membership_fact
```

Forbidden sources remain unused by B-track V2 filter implementation:

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

## Tests Added

Added a contract-driven test:

```text
test_b_track_v2_filter_apis_match_visibility_contract_default_allowlists
```

This test loads `docs/B_TRACK_V2_FIELD_VISIBILITY_POLICY_IMPLEMENTATION_CONTRACT.json` and verifies:

```text
default item key set == endpoint item_allowlist
forbidden default fields absent
membership raw_payload absent
include=detail / include=audit do not expand fields
logical source labels remain n6_display_*_cache
```

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

## Next Gate

```text
B_TRACK_V2_FIELD_VISIBILITY_POLICY_POST_REVIEW_GATE
```
