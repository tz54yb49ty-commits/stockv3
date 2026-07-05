# N6 UI Detail Drawer Trigger Fact Repair

Status: IMPLEMENTATION_PASS

Gate: N6_UI_DETAIL_DRAWER_TRIGGER_FACT_REPAIR_GATE

Layer role: N6_user

## Scope

This repair updates the N6 UI v1 administrator read-only adapter/detail drawer model so trigger facts are displayed from the repaired source action event payload before falling back to projection/card payloads.

Allowed scope:

- UI read model / adapter / drawer display logic.
- UI adapter tests.
- Repair artifact.

Forbidden scope remained unchanged:

- No database write.
- No projection/card update.
- No N5 outbox consumption or status update.
- No notification queue write.
- No worker.
- No delivery, push, voice, or mobile.
- No sim, position, PnL, real trade, proposal, order, or trade.
- No B-track modification.

## Root Cause

The detail drawer read trigger context from condition trace fallback fields, especially `period_trigger_baseline_trace.required_periods`, instead of the actual trigger fact fields carried by the repaired N5 source action event payload.

That made the UI display candidate/required periods such as `["W", "D"]` while the actual N4/N5 trigger fact was `["D"]`.

## Repair

The UI adapter now joins the N5 source event from `common_event_outbox` by `p.source_event_id` and prefers repaired event payload fields:

- `trigger_price`
- `triggered_periods`
- `baseline_source`
- `trigger_kind`
- `primary_trigger_period`

Fallbacks remain read-only and only apply when the source event payload is absent.

The adapter no longer uses `required_periods` for actual triggered period display.

## Sample Proof

Sample: `stock:SH:688690`

Expected actual trigger fact:

- condition_key: `BUY:W,D`
- trigger_kind: `trigger`
- primary_trigger_period: `D`
- trigger_price: `43.73`
- triggered_periods: `["D"]`
- baseline_source: `trigger_baseline`
- N5 action event id: `evt_51a3ea62bfb8e93407a5859107a95c0e14ad6d70`
- N4 trigger event id: `evt_61bf1423e33a28d3e19c879c71a8d24a5241bc16`

Verified UI adapter/detail output:

- condition_key: `BUY:W,D`
- trigger_kind: `trigger`
- primary_trigger_period: `D`
- trigger_price: `43.73`
- triggered_periods: `["D"]`
- baseline_source: `trigger_baseline`

## Full Coverage Proof

Run scope:

- projection_run_id: `user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- rows: 605

Before repair, using the old UI expressions:

- trigger_price missing: 605
- triggered_periods mismatch vs N4/N5 actual: 526
- baseline_source mismatch vs N4/N5 actual: 605

After repair, using the new UI adapter:

- trigger_price missing: 0
- trigger_price mismatch: 0
- triggered_periods missing: 0
- triggered_periods mismatch: 0
- baseline_source missing: 0
- baseline_source mismatch: 0
- trigger_kind missing: 0
- trigger_kind mismatch: 0
- primary_trigger_period missing: 0
- primary_trigger_period mismatch: 0

## Validation

- Focused UI adapter test: PASS.
- `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'`: PASS, 43 tests.
- `python3 -m compileall src tests scripts`: PASS.

## Next Gate

Allowed next gate:

- N6_UI_DETAIL_DRAWER_POST_REVIEW_GATE
