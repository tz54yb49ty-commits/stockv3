# N5/N6 Trigger Fact Passthrough Display Repair Closeout

Gate: `N5_N6_TRIGGER_FACT_PASSTHROUGH_DISPLAY_REPAIR_CLOSEOUT_GATE`
Layer role: `runtime_control`
Branch: `N5_N6_TRIGGER_FACT_PASSTHROUGH_DISPLAY_REPAIR`
Status: `CLOSEOUT_PASS`
Generated at: `2026-06-06T15:04:26+08:00`

## Boundary

This closeout gate is readonly except for generating this artifact pair.

It did not execute SQL, write database rows, update projection/card rows, consume or update N5 outbox, write notification queue, start a worker, trigger delivery/push/voice/mobile, mutate sim/position/PnL/real trade, generate proposal/order/trade, or modify B-track.

## Root Cause

- N4 trigger facts were correct.
- N5 event/outbox payloads originally missed trigger fact passthrough fields:
  `trigger_price`, `triggered_periods`, `all_trigger_periods`, `primary_trigger_period`,
  `trigger_kind`, `period_trigger_baseline_trace`, and `baseline_source`.
- N6 UI detail drawer previously used condition trace fallback fields, especially
  `period_trigger_baseline_trace.required_periods`, as actual `triggered_periods`.

## Repair Summary

N5 forward fix:

- Status: `IMPLEMENTATION_PASS`
- Future N5 action event/outbox payloads passthrough the trigger fact fields listed above.
- Source artifact: `docs/N5_TRIGGER_FACT_PAYLOAD_PASSTHROUGH_REPAIR_IMPLEMENTATION.json`

N5 historical payload repair:

- Status: `REPAIR_PASS`
- `common_action_event.payload_json` updated rows: `605`
- N5 `common_event_outbox.payload_json` updated rows: `605`
- Source artifact: `docs/N5_TRIGGER_FACT_PAYLOAD_HISTORICAL_REPAIR.json`
- This closeout gate did not execute that repair; it only registers the already completed repair state.

N6 UI detail drawer repair:

- Status: `POST_REVIEW_PASS`
- Source artifacts:
  - `docs/N6_UI_DETAIL_DRAWER_TRIGGER_FACT_REPAIR.json`
  - `docs/N6_UI_DETAIL_DRAWER_POST_REVIEW.json`
- UI detail drawer reads repaired N5 outbox payload first and no longer uses `required_periods` as actual triggered periods.

## Proof Summary

Live read-only proof:

| Check | Result |
|---|---:|
| `common_action_event` scoped rows | `605` |
| N5 `common_event_outbox` scoped rows | `605` |
| `trigger_price` present | `605/605` |
| `triggered_periods` present | `605/605` |
| `all_trigger_periods` present | `605/605` |
| `primary_trigger_period` present | `605/605` |
| `trigger_kind` present | `605/605` |
| `period_trigger_baseline_trace` present | `605/605` |
| `baseline_source` present | `605/605` |
| N4 joined rows | `605` |
| N5 trigger price mismatch vs N4 | `0` |
| N5 triggered periods mismatch vs N4 | `0` |
| N5 all trigger periods mismatch vs N4 | `0` |
| N5 primary trigger period mismatch vs N4 | `0` |
| N5 trigger kind mismatch vs N4 | `0` |
| N5 baseline source mismatch vs N4 | `0` |

N6 UI detail drawer proof:

| Check | Result |
|---|---:|
| `user_signal_projection` | `605` |
| `user_signal_card` | `605` |
| `user_notification_queue` | `0` |
| N5 payload join missing | `0` |
| UI trigger price missing / mismatch | `0 / 0` |
| UI triggered periods missing / mismatch | `0 / 0` |
| UI baseline source missing / mismatch | `0 / 0` |
| UI trigger kind missing / mismatch | `0 / 0` |
| UI primary trigger period missing / mismatch | `0 / 0` |

Sample `stock:SH:688690`:

| Field | Value |
|---|---|
| condition key | `BUY:W,D` |
| source action event | `evt_51a3ea62bfb8e93407a5859107a95c0e14ad6d70` |
| N4 trigger event | `evt_61bf1423e33a28d3e19c879c71a8d24a5241bc16` |
| trigger price | `43.73` |
| triggered periods | `["D"]` |
| primary trigger period | `D` |
| trigger kind | `trigger` |
| baseline source | `trigger_baseline` |

## Rollback Registry

N5 historical repair rollback:

- SQL: `sql/N5_trigger_fact_payload_historical_repair_20260605_rollback.sql`
- Exists: `true`
- Hard-fail before first `UPDATE`: `true`
- No `DELETE` / `INSERT` / `DROP` / `TRUNCATE`: `true`
- Updates only:
  - `common_action_event`
  - `common_event_outbox`
- Scope: remove only the trigger fact passthrough keys added by historical repair for the scoped N5 action run.
- Does not rollback N4/N3/N2 facts.
- Does not touch N6 projection/card/queue rows.
- Blocks if N5 outbox has delivered/delivering rows or downstream refs.

N6 UI detail drawer:

- No DB rollback needed.
- Reason: display-source-priority repair only; no projection/card/queue rows were updated by the UI repair gate.

Projection/card physical repair:

- Not performed in this branch closeout.
- If projection/card rows still need physical historical repair, enter `N6_PROJECTION_CARD_TRIGGER_FACT_HISTORICAL_REPAIR_GATE` separately.

## Forbidden Scope Proof

| Forbidden ref/scope | Count/State |
|---|---:|
| N5 outbox `ActionBlocked:pending` | `604` |
| N5 outbox `ActionExecuted:pending` | `1` |
| N5 outbox delivered/delivering | `0` |
| delivery attempts | `0` |
| inbox refs | `0` |
| checkpoint refs | `0` |
| user signal decisions | `0` |
| virtual order/trade/position/PnL refs | `0` |
| common position refs | `0` |
| user sim order/trade/position refs | `0` |
| DB writes by this gate | `false` |
| projection/card updates by this gate | `false` |
| notification queue writes | `false` |
| worker started | `false` |
| delivery/push/voice/mobile | `false` |
| sim/position/PnL/real trade | `false` |
| proposal/order/trade | `false` |
| B-track modified | `false` |

## Recommended Next Step

If projection/card rows still need physical historical repair, enter:

`N6_PROJECTION_CARD_TRIGGER_FACT_HISTORICAL_REPAIR_GATE`

Otherwise mark `N5_N6_TRIGGER_FACT_PASSTHROUGH_DISPLAY_REPAIR` complete.

## Validation

Final mechanical validation:

- JSON parse: `PASS`
- `test_n6_user_app.py`: `PASS`, 43 tests
- `test_action*.py`: `PASS`, 70 tests
- compileall: `PASS`
- `git diff --check`: `PASS`

## Result

`CLOSEOUT_PASS`

`N5_N6_TRIGGER_FACT_PASSTHROUGH_DISPLAY_REPAIR` can be marked complete.
