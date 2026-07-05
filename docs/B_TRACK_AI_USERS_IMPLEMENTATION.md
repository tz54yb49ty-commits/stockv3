# B Track AI Users Implementation

Gate: B_TRACK_AI_USERS_IMPLEMENTATION

Result: IMPLEMENTATION_PASS

Layer role: N6_user

Date: 2026-06-07

## 1. Scope

This implementation makes B Track AI Users an explicit readonly shadow-observer
surface. It does not generate signals, advice, proposals, orders, trades,
positions, PnL, or automation.

Implemented surfaces:

```text
GET /api/n6/app/v1/ai-users
GET /n6/app/ai-users
```

No database write, SQL execution outside tests, outbox consumption, outbox
status update, worker, delivery, push, voice, mobile, sim, proposal, order,
trade, position update, PnL generation, generated real signal, investment
advice, or real-trade path is introduced.

## 2. Modified Files

```text
src/ashare_v3/web/n6_app_v1.py
src/ashare_v3/web/n6_user_app.py
src/ashare_v3/web/templates/n6_app_shell.html
tests/test_n6_user_app.py
docs/B_TRACK_AI_USERS_IMPLEMENTATION.md
docs/B_TRACK_AI_USERS_IMPLEMENTATION.json
```

## 3. API Proof

The AI Users API resolves the current B Track principal and returns:

```text
component = B Track AI Users
status = readonly_shell
mode = shadow_observer
observer_policy.source = reviewed_n6_projection_only
observer_policy.generated_signal_enabled = false
observer_policy.investment_advice_enabled = false
observer_policy.auto_trade_enabled = false
observer_policy.order_enabled = false
observer_policy.real_trade_enabled = false
```

The item model exposes one readonly observer:

```text
ai_user_id = b_track_shadow_observer
role = shadow_observer
can_generate_signal = false
can_generate_advice = false
can_trade = false
can_update_position = false
```

## 4. UI Proof

`/n6/app/ai-users` renders:

```text
B Track AI Users
shadow_observer
generated_signal_enabled: False
auto_trade_enabled: False
real_trade_enabled: False
```

The page does not render auto-trade controls, one-click order controls,
investment-advice wording, generated-signal controls, position update controls,
or real-trade controls.

## 5. Forbidden Scope Proof

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
generated_signal_enabled=false
investment_advice_enabled=false
auto_trade_enabled=false
proposal_generated=false
order_generated=false
trade_generated=false
position_updated=false
pnl_generated=false
real_trade_submitted=false
```

The AI Users surface does not call A Track adapters, does not read N5 outbox,
does not read raw K or direct live market, and does not read
`condition_basis`, `condition_pool`, or `minute_target_scope`.

## 6. Verification

Fresh verification commands:

```text
PYTHONPATH=src:tests python3 -m unittest test_n6_user_app.N6UserAppTest.test_b_track_ai_users_api_is_readonly_shadow_observer test_n6_user_app.N6UserAppTest.test_b_track_ai_users_page_renders_shadow_observer_without_advice_or_trade_controls
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
```

Observed results:

```text
AI Users targeted tests: Ran 2 tests, OK
test_n6_user_app.py: Ran 54 tests, OK
```

## 7. Next Gate

```text
B_TRACK_AI_USERS_POST_REVIEW
```
