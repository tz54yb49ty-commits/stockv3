# N5 Canonical Action Flow Dry-Run / Contract Alignment Report

## Summary

- layer_role: N5_action
- mode: dry-run / contract / tests alignment only
- result: IMPLEMENTATION_PASS
- database_writes: false
- n4_outbox_consumed: false
- inbox_checkpoint_updated: false
- schema_migration_executed: false
- worker_started: false
- n6_user_layer_touched: false
- real_trade_touched: false

## Canonical Rules Implemented In Planning

- TriggerMatched is the only N5 action confirmation entry.
- TriggerPendingMarketData produces quality/no-op planning only and never starts action confirmation.
- TriggerStateChanged is a state gate only. trigger_live=true can wake or update tracking context; trigger_live=false expires/stops tracking.
- Runtime signal_type accepts only B_BUY and S_SELL.
- BUY_HINT and SELL_HINT are preserved only as condition_key/original_condition_key/trace_json.
- Deprecated runtime signal_type values BUY_HINT, SELL_HINT, B_BUY_30M_VOL, and S_SELL_30M_SHRINK are blocked in dry-run planning.
- final_action_mark is written only when confirmation_status=passed and action_state=executed.
- final_action_mark is limited to normal, 30m_volume, and 30m_shrink.
- Canonical output event planning uses ActionEligible, ActionBlocked, ActionExecuted, and ActionSkipped.
- ActionExecuted means N5 action confirmation fact only; it does not mean real order, sim, N6 display, voice, mobile, or trade intent.

## Planner Fields

Each planned action candidate now carries:

- source_trigger_event_id
- source_trigger_event_type
- signal_type
- condition_key
- original_condition_key
- trigger_mark_candidate
- action_mark_candidate
- final_action_mark
- action_state
- confirmation_status
- trigger_live
- minute_boundary_status
- action_event_type
- trace_json

## Compatibility Boundary

The current migrated SQL schema is intentionally not changed in this gate. Static schema review now reports canonical divergence instead of passing silently:

- missing TriggerStateChanged input literal
- missing ActionEligible / ActionBlocked / ActionExecuted / ActionSkipped output literals
- missing source_trigger_state_id
- missing original_condition_key
- missing action_state
- missing confirmation_status
- missing action_policy
- missing trace_json

This means execute remains contract-blocked until a later explicit schema alignment / migration gate.

## Verification

- PYTHONPATH=src python3 -m unittest discover -s tests: passed, 978 tests
- No database command was executed.
- No N4 outbox row was consumed.
- No worker was started.
