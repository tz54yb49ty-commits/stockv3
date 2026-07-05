# N4 Worker Bounded Smoke 20260608 Unified Output Probe

Smoke run: `n4_worker_bounded_smoke_20260608_unified_output_probe`
Consumer: `n4_trigger_worker_v1_bounded_smoke_probe`

Result: `DRY_RUN_PASS`

## Source Selection

Pending source events: `2155`; selected: `5`.

| outbox_id | identity_key | event_time | payload_snapshot_id | payload_data_quality_status |
|---|---|---|---|---|
| 223581 | board:TDX:881002 | 2026-06-08 15:00:00+08:00 | 4013 | passed |
| 223582 | board:TDX:881005 | 2026-06-08 15:00:00+08:00 | 4014 | passed |
| 223583 | board:TDX:881007 | 2026-06-08 15:00:00+08:00 | 4015 | passed |
| 223584 | board:TDX:881008 | 2026-06-08 15:00:00+08:00 | 4016 | passed |
| 223585 | board:TDX:881011 | 2026-06-08 15:00:00+08:00 | 4017 | passed |

## JSONB Serialization Proof

`{'selected_source_events_json_safe': True, 'inbox_payload_json_safe': True, 'inbox_raw_json_safe': True, 'checkpoint_payload_json_safe': True, 'run_raw_json_safe': True, 'quality_details_json_safe': True, 'outbox_payload_json_safe': True}`

## Plan Summary

TriggerMatched / TriggerPendingMarketData / TriggerStateChanged: `0/0/0`
