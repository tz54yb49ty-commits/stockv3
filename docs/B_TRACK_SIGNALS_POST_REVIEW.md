# B Track Signals Post Review

Gate: B_TRACK_SIGNALS_POST_REVIEW

Result: POST_REVIEW_PASS

Layer role: N6_user

Date: 2026-06-07

This gate performed a read-only post-review of the B Track Signals page and
API after `B_TRACK_SIGNALS_IMPLEMENTATION_GATE`. It did not write database
rows, execute SQL, consume outbox, update outbox status, start workers, trigger
delivery, push, voice, mobile, sim, position, PnL, proposal, order, trade, or
real-trade paths.

## Source Artifacts

```text
docs/B_TRACK_READONLY_REMEDIATION_CONTRACT.md
docs/B_TRACK_READONLY_REMEDIATION_CONTRACT.json
docs/B_TRACK_READONLY_REMEDIATION_DRY_RUN.md
docs/B_TRACK_READONLY_REMEDIATION_DRY_RUN.json
docs/B_TRACK_SIGNALS_IMPLEMENTATION.md
docs/B_TRACK_SIGNALS_IMPLEMENTATION.json
```

## Reviewed Surfaces

```text
GET /api/n6/app/v1/signals
GET /api/n6/app/v1/signals/{user_signal_projection_id}
GET /n6/app/signals
```

The B Track route scan found only `GET` routes under `/api/n6/app/v1` and
`/n6/app`.

## Adapter Proof

The B Track Signals adapter is independent from A Track. The reviewed adapter:

```text
PostgresN6UserRepository.fetch_app_signals
PostgresN6UserRepository.fetch_app_signal_detail
```

does not call:

```text
fetch_ui_v1_signals
fetch_ui_v1_signal_detail
_ui_v1_signal_from_sql
```

The adapter reads reviewed N6 rows through:

```text
user_signal_projection
user_projection_run
user_signal_card
n6_principal principal scope
```

It does not directly join `common_event_outbox` for B Track Signals.

## Principal Scope Proof

Both API routes resolve the current principal before reading signals. The
adapter receives all required scope inputs:

```text
principal_id
principal_type
user_id
```

The SQL scope includes `n6_principal` with matching `principal_id`,
`principal_type`, `owner_user_id`, and `principal_status='active'`.

## Allowlist Proof

The implemented source policy exposes the required allowlist:

```text
reviewed N6 projections
reviewed signal cards
n6_display_stock_condition_cache
n6_display_index_condition_cache
n6_display_board_condition_cache
n6_display_index_membership_cache
n6_display_board_membership_cache
```

Display cache and membership cache entries are readonly explanation sources.
They are not used to recompute N2 conditions, rebuild `condition_pool`, rebuild
`minute_target_scope`, construct N4/N5 signals, or infer market scope.

## Forbidden Scope Proof

The implemented source policy exposes the required forbidden sources:

```text
raw K
N1 raw facts
direct live market
N4 raw facts bypass
N5 raw facts bypass
condition_basis
condition_pool
minute_target_scope
unreviewed outbox / raw facts
```

The API proof flags are all false:

```text
raw_k_read=false
n1_raw_facts_read=false
direct_live_market_read=false
n4_raw_facts_bypass=false
n5_raw_facts_bypass=false
condition_basis_read=false
condition_pool_read=false
minute_target_scope_read=false
unreviewed_outbox_or_raw_facts_read=false
```

## API Proof

Signal list and detail responses include the expected readonly fields:

```text
asset_kind
display_name
display_code
identity_key
direction
action_state
action_mark
blocked_reason
condition_trace
evidence_chain
quality_status
source_run_id
projection_run_id
event_time
tags
detail_page
```

The `evidence_chain` includes:

```text
N2_display_basis
N3_market_data
N4_trigger
N5_action
N6_projection
```

## UI Proof

`/n6/app/signals` renders a readonly table with:

```text
trade_date
asset_kind
display_name / display_code
identity_key
direction
condition trace
action_state
action_mark
blocked_reason
tags
quality_status
event_time
N5 source_run_id
N6 projection_run_id
```

The reviewed page does not render buy buttons, sell buttons, one-click order
controls, auto-trade toggles, or investment-advice wording for Signals.

`BUY_HINT` and `SELL_HINT` render only as condition trace:

```text
source_trace_only_not_advice
condition_source_only_not_tip_stock_or_advice
```

## Validation

Fresh validation before this artifact was written:

```text
PYTHONPATH=src python3 -m compileall src/ashare_v3/web/n6_app_v1.py src/ashare_v3/web/n6_user_app.py
python3 route scan for /api/n6/app/v1 and /n6/app
python3 JSON parse for remediation and implementation artifacts
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
```

Observed results:

```text
compileall: exit 0
route scan: ROUTE_SCAN_GET_ONLY_PASS
JSON parse: PASS
unittest: Ran 48 tests, OK
```

## Decision

```text
POST_REVIEW_PASS
P0/P1/P2 = 0/0/0
```

Next gate:

```text
B_TRACK_SIGNALS_CLOSEOUT
```
