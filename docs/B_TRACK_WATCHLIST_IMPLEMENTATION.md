# B Track Watchlist Implementation

Gate: B_TRACK_WATCHLIST_IMPLEMENTATION

Result: IMPLEMENTATION_PASS

Layer role: N6_user

Date: 2026-06-07

## 1. Scope

This implementation upgrades B Track Watchlist from a planned placeholder to a
readonly projection list derived from reviewed N6 signals/cards. It does not
persist a user watchlist and does not add mutation controls.

Implemented surfaces:

```text
GET /api/n6/app/v1/watchlist
GET /n6/app/watchlist
```

No database write, SQL execution outside tests, outbox consumption, outbox
status update, worker, delivery, push, voice, mobile, sim, proposal, order,
trade, position update, PnL generation, or real-trade path is introduced.

## 2. Modified Files

```text
src/ashare_v3/web/n6_app_v1.py
src/ashare_v3/web/n6_user_app.py
src/ashare_v3/web/templates/n6_app_shell.html
tests/test_n6_user_app.py
docs/B_TRACK_WATCHLIST_IMPLEMENTATION.md
docs/B_TRACK_WATCHLIST_IMPLEMENTATION.json
```

## 3. API Proof

The Watchlist API resolves the current B Track principal and preserves:

```text
principal_id
principal_type
user_id
```

The adapter reads only reviewed B Track signal projection inputs:

```text
reviewed N6 projections
reviewed signal cards
n6_display_stock_condition_cache
n6_display_index_condition_cache
n6_display_board_condition_cache
n6_display_index_membership_cache
n6_display_board_membership_cache
```

Each item includes:

```text
asset_kind
display_name
display_code
identity_key
status
action.action_state
action.action_mark
action.blocked_reason
condition_source
recent_signal
readonly flags
```

## 4. UI Proof

`/n6/app/watchlist` renders a readonly table with:

```text
asset_kind
name / code
identity_key
status
Action
condition source
recent signal
```

It renders `ActionBlocked` / `ActionExecuted`, `blocked_reason`, and
`n6_display_*` condition source labels as readonly evidence.

## 5. Mutation Controls

The Watchlist controls are explicitly disabled:

```text
add_enabled=false
delete_enabled=false
sort_enabled=false
sort_persist_enabled=false
source=reviewed_n6_projection_only
```

The page/API do not provide add, delete, reorder persistence, buy/sell,
one-click order, auto-trade, advice, position update, or PnL controls.

## 6. Forbidden Scope Proof

Confirmed by implementation and tests:

```text
database_written=false
sql_executed=false
outbox_consumed=false
outbox_status_updated=false
worker_started=false
delivery_triggered=false
push_triggered=false
voice_triggered=false
mobile_triggered=false
proposal_generated=false
order_generated=false
trade_generated=false
position_updated=false
pnl_generated=false
real_trade_submitted=false
user_watchlist_written=false
```

The Watchlist does not call A Track signal adapters, does not read N5 outbox,
does not read raw K or direct live market, does not bypass reviewed N6
projection/card data, and does not read `condition_basis`, `condition_pool`, or
`minute_target_scope`.

## 7. Verification

Fresh verification commands:

```text
PYTHONPATH=src:tests python3 -m unittest test_n6_user_app.N6UserAppTest.test_b_track_watchlist_api_is_readonly_projection_from_reviewed_signals test_n6_user_app.N6UserAppTest.test_b_track_watchlist_page_renders_items_without_mutation_controls
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
```

Observed results:

```text
watchlist targeted tests: Ran 2 tests, OK
test_n6_user_app.py: Ran 52 tests, OK
```

## 8. Next Gate

```text
B_TRACK_WATCHLIST_POST_REVIEW
```
