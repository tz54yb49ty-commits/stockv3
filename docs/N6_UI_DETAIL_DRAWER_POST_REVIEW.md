# N6 UI Detail Drawer Post Review

Status: POST_REVIEW_PASS

Gate: N6_UI_DETAIL_DRAWER_POST_REVIEW_GATE

Layer role: N6_user

## Objective

Close out the N6 UI detail drawer trigger fact repair and verify that the administrator read-only UI now displays actual N4/N5 trigger facts instead of condition required-period fallback fields.

## Inputs

- Repair artifact: `docs/N6_UI_DETAIL_DRAWER_TRIGGER_FACT_REPAIR.md`
- Repair artifact JSON: `docs/N6_UI_DETAIL_DRAWER_TRIGGER_FACT_REPAIR.json`
- Projection run: `user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`

## Scoped Row Proof

- user_signal_projection rows: 605
- user_signal_card rows: 605
- user_notification_queue rows: 0

## Trigger Fact Proof

The UI adapter was checked against N4/N5 source event payloads for all 605 rows.

Result:

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

## Sample Proof

Sample identity: `stock:SH:688690`

- condition_key: `BUY:W,D`
- trigger_kind: `trigger`
- primary_trigger_period: `D`
- trigger_price: `43.73`
- triggered_periods: `["D"]`
- baseline_source: `trigger_baseline`
- N5 source event id: `evt_51a3ea62bfb8e93407a5859107a95c0e14ad6d70`
- N4 trigger event id: `evt_61bf1423e33a28d3e19c879c71a8d24a5241bc16`

## UI Alignment

The N6 UI detail drawer is aligned with the repaired N4/N5 source payloads for actual trigger facts:

- Actual trigger price is shown.
- Actual triggered periods are shown.
- Baseline source is shown from the actual trigger fact.
- Trigger kind and primary trigger period are shown from the same source priority.
- `period_trigger_baseline_trace.required_periods` is not used as actual triggered periods.

## Forbidden Scope Proof

This post-review was read-only except for writing closeout artifacts.

- Database writes: false
- Projection/card updates: false
- N5 outbox consumption: false
- N5 outbox status updates: false
- Notification queue writes: false
- Worker started: false
- Delivery/push/voice/mobile: false
- Sim/position/PnL/real trade: false
- Proposal/order/trade generation: false
- B-track modification: false

## Validation

- JSON parse: PASS
- `python3 -m compileall src tests scripts`: PASS
- `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'`: PASS, 43 tests
- `git diff --check`: PASS

## Result

POST_REVIEW_PASS

The repair is ready for runtime_control closeout registration.
