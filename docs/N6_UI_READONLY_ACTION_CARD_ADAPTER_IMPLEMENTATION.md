# N6 UI Readonly Action Card Adapter Implementation

Status: IMPLEMENTATION_PASS

Layer role: N6_user

Date: 2026-06-06

This implementation fixes the Track A `N6_UI_v1_ADMIN_CONSOLE` read-only action
card adapter. It does not write business data, consume or update N5 outbox,
write `user_notification_queue`, start workers, deliver/push/voice/mobile, run
sim/position/PnL/real trade, generate proposal/order/trade, modify B-track
schema, or expand Track A into a multi-user front office.

## 1. Modified Files

```text
src/ashare_v3/web/n6_user_app.py
src/ashare_v3/web/n6_ui_v1.py
tests/test_n6_user_app.py
docs/N6_UI_READONLY_ACTION_CARD_ADAPTER_IMPLEMENTATION.md
docs/N6_UI_READONLY_ACTION_CARD_ADAPTER_IMPLEMENTATION.json
```

## 2. Signals API Fix

Fixed function:

```text
PostgresN6UserRepository.fetch_ui_v1_signals()
```

Implementation:

```text
empty filters no longer bind NULL filter parameters
normal filters only bind supplied filter parameters
WHERE clause is built dynamically for non-empty filters
default scope is latest passed user_projection_run
route remains GET /api/n6/ui/v1/signals
no mutation route added
```

The default latest-run scope prevents historical N6 projections from mixing
with the current 20260605 action-card adapter view.

## 3. Action Card Proof

Real DB read-only proof:

```text
empty filters result=605
normal filters action_state=blocked&blocked_reason=price_confirmation_failed result=305
ActionExecuted=1
ActionBlocked=604
```

Blocked reason distribution:

```text
price_confirmation_failed=305
metric_missing=289
amount_confirmation_failed=10
```

## 4. Detail Proposal Wording

Track A detail now calls:

```text
proposal_eligibility_model(row, track="admin_console")
```

For `ActionExecuted`, Track A returns:

```text
behavior=projection_only
future_eligible=false
proposal_generated=false
order_generated=false
trade_generated=false
position_updated=false
pnl_generated=false
```

The Track A response no longer displays:

```text
proposal_candidate
```

B-track read-only app shell keeps its existing proposal-candidate planning
semantics because its callers still use the default model mode.

## 5. Safety Banner

Safety labels now include:

```text
READ ONLY
NO ORDER
NO TRADE
NO POSITION UPDATE
NO REAL TRADE
NOT INVESTMENT ADVICE
```

## 6. Boundary

```text
database_written=false
write_notification_queue=false
consume_n5_outbox=false
update_n5_outbox_status=false
start_worker=false
delivery=false
push=false
voice=false
mobile=false
sim=false
position=false
pnl=false
real_trade=false
proposal=false
order=false
trade=false
modify_b_track_schema=false
```

## 7. Verification

```text
TDD red proof:
  proposal_candidate wording test failed before implementation
  nullable filter param SQL-shape test failed before implementation
  latest projection run scope test failed before implementation

Targeted tests:
  test_n6_user_app.py = 39 tests OK

Real DB read-only proof:
  REAL_DB_READONLY_API_PROOF_OK

Static checks:
  JSON parse OK
  route method scan GET-only OK
  boundary scan OK
  compileall OK
  git diff --check OK
```

## 8. Result

```text
implementation_result=IMPLEMENTATION_PASS
remaining_blockers=none
allow_post_review_gate=true
next_allowed_gate=N6_UI_READONLY_REFRESH_POST_REVIEW_GATE
```
