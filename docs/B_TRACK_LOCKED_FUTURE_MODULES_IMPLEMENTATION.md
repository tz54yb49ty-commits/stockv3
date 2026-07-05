# B Track Locked Future Modules Implementation

Gate: B_TRACK_LOCKED_FUTURE_MODULES_IMPLEMENTATION

Result: IMPLEMENTATION_PASS

Layer role: N6_user

Date: 2026-06-07

## 1. Scope

This implementation locks future B Track V1 modules behind explicit readonly
shells. The pages and APIs display planned/locked status only. They do not read
position, PnL, proposal, order, trade, outbox, raw K, direct live market, or
unreviewed upstream facts.

Implemented locked surfaces:

```text
GET /api/n6/app/v1/proposals
GET /api/n6/app/v1/portfolio
GET /api/n6/app/v1/pnl
GET /api/n6/app/v1/leaderboard
GET /n6/app/proposals
GET /n6/app/portfolio
GET /n6/app/pnl
GET /n6/app/leaderboard
```

## 2. Modified Files

```text
src/ashare_v3/web/n6_app_v1.py
src/ashare_v3/web/n6_user_app.py
src/ashare_v3/web/templates/n6_app_shell.html
tests/test_n6_user_app.py
docs/B_TRACK_LOCKED_FUTURE_MODULES_IMPLEMENTATION.md
docs/B_TRACK_LOCKED_FUTURE_MODULES_IMPLEMENTATION.json
```

## 3. API Proof

Each future module resolves the current B Track principal and returns a locked
model:

```text
locked = true
readonly = true
items = []
controls.entry_enabled = false
controls.proposal_enabled = false
controls.order_enabled = false
controls.trade_enabled = false
controls.position_update_enabled = false
controls.pnl_generation_enabled = false
controls.leaderboard_materialization_enabled = false
controls.auto_trade_enabled = false
controls.real_trade_enabled = false
```

Portfolio and PnL no longer call `fetch_app_positions` or
`fetch_app_pnl_snapshots` in B Track V1 locked mode.

## 4. UI Proof

The locked module pages render locked state and disabled controls:

```text
locked: True
entry_enabled: False
proposal_enabled: False
order_enabled: False
trade_enabled: False
position_update_enabled: False
pnl_generation_enabled: False
real_trade_enabled: False
```

The pages do not render buy/sell controls, one-click order, auto-trade,
investment-advice wording, position update, PnL generation, or real-trade
controls.

## 5. Forbidden Scope Proof

Confirmed false:

```text
database_written
sql_executed
outbox_consumed
outbox_status_updated
worker_started
delivery_triggered
push_triggered
voice_triggered
mobile_triggered
proposal_generated
order_generated
trade_generated
position_updated
pnl_generated
leaderboard_materialized
real_trade_submitted
position_rows_read
pnl_rows_read
raw_k_read
direct_live_market_read
condition_basis_read
condition_pool_read
minute_target_scope_read
unreviewed_outbox_or_raw_fact_read
```

## 6. Verification

Fresh verification commands:

```text
PYTHONPATH=src:tests python3 -m unittest test_n6_user_app.N6UserAppTest.test_b_track_locked_future_modules_apis_are_readonly_without_data_reads test_n6_user_app.N6UserAppTest.test_b_track_locked_future_modules_pages_render_locked_state_without_trade_controls test_n6_user_app.N6UserAppTest.test_b_track_empty_planned_apis_and_disclaimers_are_get_only_read_only
python3 -m compileall src/ashare_v3/web/n6_app_v1.py src/ashare_v3/web/n6_user_app.py
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
git diff --check
```

Observed results:

```text
Locked future targeted tests: Ran 3 tests, OK
compileall: exit 0
test_n6_user_app.py: Ran 56 tests, OK
git diff --check: exit 0
```

## 7. Next Gate

```text
B_TRACK_LOCKED_FUTURE_MODULES_POST_REVIEW
```
