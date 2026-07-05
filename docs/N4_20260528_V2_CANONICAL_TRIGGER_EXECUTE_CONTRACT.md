# N4 20260528 V2 Trigger Execute Contract

- result: `CONTRACT_PASS`
- execute_run_id: `trigger_execute_20260528_condition_layer_20260527_source_20260527_v2`
- context_run_id: `trigger_context_snapshot_20260528_condition_layer_20260527_source_20260527_v2`
- snapshot_run_id: `realtime_snapshot_20260528_market_data_subscription_20260528_condition_layer_20260527_source_20260527_v2`
- event_schema_version: `v2-canonical-trigger-action-runtime`
- runner_ready: `True`

## Expected Future Writes

- TriggerMatched: `4285`
- TriggerPendingMarketData: `4602`
- TriggerStateChanged: `8887`
- common_trigger_state: `8887`
- common_trigger_match: `8887`
- common_event_outbox: `17774`

## Canonical Payload

- runtime signal_type: `B_BUY`, `S_SELL`
- trigger_mark_candidate: `normal`, `30m_volume`, `30m_shrink`
- trace fields preserve `condition_key`, `original_condition_key`, `legacy_signal_type`
- deprecated 30m and hint values are forbidden in runtime `signal_type`

## Boundary

- preflight refresh writes no database rows
- final execute requires `--execute --user-confirmed`
- N5/N6 remain blocked until N4 outbox execute is separately confirmed and passed