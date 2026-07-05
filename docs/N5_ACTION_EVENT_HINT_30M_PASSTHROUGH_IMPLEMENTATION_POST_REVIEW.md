# N5 Action Event HINT 30m Passthrough Implementation Post Review

Result: `POST_REVIEW_PASS`

Gate: `N5_ACTION_EVENT_HINT_30M_PASSTHROUGH_IMPLEMENTATION_POST_REVIEW_GATE`

Layer role: `runtime_control`

This gate is read-only. It did not modify code, execute N5, write the database, consume or update N4 outbox, write N5 inbox/checkpoint, enter N6, start a worker, or execute rollback SQL.

## Implementation Proof Summary

The implementation report exists and parses as JSON:

- implementation result: `IMPLEMENTATION_PASS`
- fixed function: `src/ashare_v3/action/execute.py::build_action_event_passthrough_payload`
- `primary_trigger_period` now comes only from explicit formal primary fields:
  - `row.primary_trigger_period`
  - `source_payload.primary_trigger_period`
- fallback to `row.trigger_period` / `source_payload.trigger_period`: removed
- `src/ashare_v3/events/models.py` formal-period 30m guard: not relaxed
- `src/ashare_v3/action/event_factory.py`: no silent deletion of invalid fields to hide upstream payload bugs

The function-level static proof confirms:

```text
primary_trigger_period = row.get("primary_trigger_period") or source_payload.get("primary_trigger_period")
```

and that this assignment does not reference `row.get("trigger_period")` or `source_payload.get("trigger_period")`.

## HINT 30m Semantic Proof

Legal HINT passthrough remains:

```json
{
  "trigger_kind": "hint",
  "condition_key": "BUY_HINT or SELL_HINT",
  "trigger_period": "30m",
  "triggered_periods": [],
  "all_trigger_periods": [],
  "primary_trigger_period": null,
  "trigger_price": "present",
  "n5_entry_allowed": true
}
```

`build_n5_action_event` accepts legal HINT 30m passthrough after the fix.

Illegal cases still block:

- ordinary `trigger_kind=trigger + trigger_period=30m`
- `30m` inside `triggered_periods`
- `30m` inside `all_trigger_periods`
- `30m` inside `primary_trigger_period`

## Regression Proof

Fresh targeted validation passed:

| Command | Result |
|---|---|
| `PYTHONPATH=src python3 -m unittest tests/test_action_execute.py` | `PASS (29 tests)` |
| `PYTHONPATH=src python3 -m unittest tests/test_n4_v4_enforcement.py` | `PASS (19 tests)` |
| `PYTHONPATH=src python3 -m unittest tests/test_trigger_projection_matcher_execute.py` | `PASS (19 tests)` |
| `python3 -m compileall src/ashare_v3/action src/ashare_v3/events tests` | `PASS` |

Covered behavior:

- legal `BUY_HINT` 30m passthrough passes
- legal `SELL_HINT` 30m passthrough passes
- HINT 30m `primary_trigger_period` is not fallback-filled as `30m`
- legal HINT 30m event construction no longer raises `EventContractError`
- ordinary 30m trigger still blocks
- `30m` in formal period fields still blocks
- `TriggerPendingMarketData` remains quality-only with no action output

## Baseline Proof

Live DB read-only baseline confirms the failed N5 retry left no target rows:

| Target | Rows |
|---|---:|
| `common_action_run` | 0 |
| `common_action_quality_item` | 0 |
| `stock_action_fact` | 0 |
| `index_action_fact` | 0 |
| `board_action_fact` | 0 |
| `common_action_event` | 0 |
| N5 `common_event_outbox` | 0 |
| N5 `common_event_inbox` | 0 |
| N5 consumer checkpoint | 0 |

N4 retry source remains unchanged:

| Proof | Count |
|---|---:|
| `TriggerMatched / pending` | 119 |
| `TriggerPendingMarketData / pending` | 3801 |
| delivered / delivering | 0 / 0 |
| `common_trigger_match` | 119 |
| `common_trigger_state` | 3920 |

Downstream refs remain zero:

| Target | Rows |
|---|---:|
| `user_projection_run` | 0 |
| `user_signal_projection` | 0 |
| `user_signal_card` | 0 |
| `user_notification_queue` | 0 |
| `common_position_state` | 0 |
| `common_position_event` | 0 |
| `user_sim_order` | 0 |
| `user_sim_trade` | 0 |
| `user_sim_position` | 0 |

## Forbidden Scope Proof

- N5 execute: `false`
- DB write by runtime_control: `false`
- action fact/event/outbox written: `false`
- N4 outbox consumed or updated: `false`
- N5 inbox/checkpoint written: `false`
- N6 entered: `false`
- worker started: `false`
- rollback SQL executed: `false`
- delivery/push/voice/mobile: `false`
- sim/position/PnL/real trade: `false`
- proposal/order/trade: `false`
- old system touched: `false`

## Validation

- implementation report JSON parse: `PASS`
- contract JSON parse: `PASS`
- failed execute report JSON parse: `PASS`
- N4 post-review JSON parse: `PASS`
- targeted tests: `PASS`
- compileall: `PASS`
- code diff/static proof: `PASS`
- live DB baseline proof: `PASS`
- post-review JSON parse: `PASS`
- `git diff --check`: `PASS`

## Next Gate

Allowed next gate:

`N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_REGENERATION_GATE`
