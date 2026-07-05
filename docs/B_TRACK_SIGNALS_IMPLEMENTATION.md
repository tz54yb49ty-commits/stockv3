# B Track Signals Implementation

Gate: B_TRACK_SIGNALS_IMPLEMENTATION_GATE

Result: IMPLEMENTATION_PASS

Layer role: N6_user

Date: 2026-06-07

## 1. Scope

This implementation makes the B Track Signals page and API independent from
A Track signal adapters.

Implemented surfaces:

```text
GET /api/n6/app/v1/signals
GET /api/n6/app/v1/signals/{user_signal_projection_id}
GET /n6/app/signals
```

No database write, SQL execution outside tests, outbox consumption, worker,
delivery, proposal, order, trade, position, PnL, sim, voice, mobile, or real
trade path is introduced.

## 2. Modified Files

```text
src/ashare_v3/web/n6_app_v1.py
src/ashare_v3/web/n6_user_app.py
src/ashare_v3/web/templates/n6_app_shell.html
tests/test_n6_user_app.py
docs/B_TRACK_SIGNALS_IMPLEMENTATION.md
docs/B_TRACK_SIGNALS_IMPLEMENTATION.json
```

## 3. API Proof

The B Track Signals API now resolves the current principal first and passes the
full scope into the adapter:

```text
principal_id
principal_type
user_id
```

The Postgres adapter reads reviewed N6 rows through a B Track-owned query:

```text
user_signal_projection
user_projection_run
user_signal_card
n6_principal for principal scope
```

It does not call:

```text
fetch_ui_v1_signals
fetch_ui_v1_signal_detail
_ui_v1_signal_from_sql
```

The detail API returns the same readonly model for one signal:

```text
GET /api/n6/app/v1/signals/{user_signal_projection_id}
```

## 4. UI Proof

The `/n6/app/signals` HTML page renders only readonly table fields:

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

It does not render buy/sell buttons, one-click order controls, auto-trade
toggles, or investment-advice wording.

## 5. Allowlist

B Track source policy now explicitly allows:

```text
reviewed N6 projections
reviewed signal cards
n6_display_stock_condition_cache
n6_display_index_condition_cache
n6_display_board_condition_cache
n6_display_index_membership_cache
n6_display_board_membership_cache
```

Display cache entries are exposed as readonly explanation sources only. The
adapter does not recompute N2 conditions, construct N4/N5 signals, or infer
market scope from membership data.

## 6. Forbidden Scope Proof

B Track source policy now explicitly forbids:

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

Proof flags exposed by the API are all false:

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

## 7. Evidence Chain

Each signal item includes a readonly chain:

```text
N2_display_basis
N3_market_data
N4_trigger
N5_action
N6_projection
```

`BUY_HINT` and `SELL_HINT` are rendered only as condition trace. They are not
rendered as tip stocks, recommendations, or investment advice.

## 8. Verification

Fresh verification commands:

```text
PYTHONPATH=src python3 -m compileall src/ashare_v3/web/n6_app_v1.py src/ashare_v3/web/n6_user_app.py
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
python3 route scan for /api/n6/app/v1 and /n6/app
```

Observed results:

```text
compileall: exit 0
unittest: Ran 48 tests, OK
route scan: ROUTE_SCAN_GET_ONLY_PASS
```

## 9. Next Gate

```text
B_TRACK_SIGNALS_POST_REVIEW
```

