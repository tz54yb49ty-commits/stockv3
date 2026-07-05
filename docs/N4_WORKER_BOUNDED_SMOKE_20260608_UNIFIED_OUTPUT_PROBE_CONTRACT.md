# N4 Worker Bounded Smoke 20260608 Unified Output Probe

Smoke run: `n4_worker_bounded_smoke_20260608_unified_output_probe`
Consumer: `n4_trigger_worker_v1_bounded_smoke_probe`

Result: `CONTRACT_PASS`

## Planned Write Scope

`{'common_trigger_run': 1, 'common_trigger_quality_item': 2, 'common_event_inbox': 5, 'common_event_consumer_checkpoint': 5, 'common_trigger_state': 0, 'common_trigger_match': 0, 'common_event_outbox': 0}`

Future execute may only write scoped N4 smoke rows and must not update N3 outbox status or enter N5/N6.
