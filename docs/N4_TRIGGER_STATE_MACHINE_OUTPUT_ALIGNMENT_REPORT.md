# N4 Trigger State Machine Output Alignment Report

- result: `ALIGNMENT_PASS`
- layer_role: `N4_trigger`
- gate: `N4_TRIGGER_STATE_MACHINE_OUTPUT_ALIGNMENT_GATE`
- date: `2026-06-13`

## Root Cause

20260612 full-day N4 replay runner evaluated N3 action-confirmation metric rows as isolated outcome facts. It emitted `TriggerMatched` for the first live minute and suppressed sustained matches, but it did not load/maintain prior trigger state and did not broadcast material state changes. Therefore `matched -> inactive`, period changes, and projection-state changes never became `TriggerStateChanged`.

N5 already has dry-run semantics for `TriggerStateChanged(trigger_live=false) -> ActionSkipped(action_state=expired)`, but it cannot produce `ActionSkipped` if N4 never emits the state event.

## Code Repair Summary

- `scripts/run_v3_20260612_n4_full_day_trigger_replay_once.py`
  - uses `build_transition_event_plans` from N4 state-transition helpers.
  - fixed state key to `trade_date|asset_kind|identity_key|direction|signal_type|condition_key`.
  - maps metric-ready-but-not-satisfied plans to `inactive`, not `TriggerPendingMarketData`.
  - emits `TriggerMatched` only for new action-entry transitions.
  - emits `TriggerStateChanged` for activation, deactivation, period upgrade/downgrade, and projection changes.
  - keeps `TriggerPendingMarketData` only for insufficient evidence.
  - blocks the legacy execute path before DB write if state-machine `TriggerStateChanged` plans exist, forcing the next execute contract gate to handle persistence explicitly.

## Proof

- `matched -> inactive` now yields `TriggerStateChanged` with `trigger_live=false`, `current_status=inactive`, `state_change_reason=deactivated`.
- `matched -> matched` period upgrade yields exactly one `TriggerStateChanged` and no second `TriggerMatched`.
- direction switch is represented as old direction `TriggerStateChanged live=false` plus new direction `TriggerMatched`.
- repeated identical matched state does not emit duplicate state events via the underlying helper.
- `TriggerStateChanged` plans have `writes_common_trigger_match=false` and `is_n5_action_entry=false`.

## N5 Status

No N5 code was changed in this N4 gate. Existing N5 dry-run tests prove:

- `TriggerStateChanged live=false` maps to `ActionSkipped`.
- `TriggerStateChanged live=true` does not start action confirmation.
- `TriggerMatched` action-confirmation behavior remains unchanged.

Any N5 execute-path repair, if later needed, must be handled under `layer_role=N5_action`.

## Forbidden Scope

- N4 execute: `false`
- database writes: `false`
- outbox/inbox/checkpoint consumption or update: `false`
- worker started: `false`
- N5/N6 entered: `false`
- delivery/push/voice/mobile: `false`
- sim/position/order/trade/real_trade: `false`

## Validation

- `PYTHONPATH=src:scripts python3 -m unittest tests.test_v3_20260612_n4_trigger_state_machine tests.test_n4_worker_state_transition tests.test_action_dry_run`
- `PYTHONPATH=src:scripts python3 -m unittest tests.test_v3_20260612_full_day_replay_plan tests.test_trigger_action_confirmation_metric_matcher`
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_trigger*.py'`
- `python3 -m compileall scripts src/ashare_v3/trigger tests`
- `PYTHONPATH=src python3 scripts/check_n4_contract.py`
- `python3 -m json.tool docs/N4_TRIGGER_STATE_MACHINE_OUTPUT_ALIGNMENT_REPORT.json >/dev/null`
- `git diff --check`

## Next Gate

Allowed next gate:

```text
N4_TRIGGER_STATE_MACHINE_DRY_RUN_PREFLIGHT_GATE
```

That gate should regenerate dry-run / contract / preflight / rollback artifacts and decide the exact scoped execute writer requirements before any N4 DB write.
