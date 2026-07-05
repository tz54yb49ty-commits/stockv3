# N4 20260529 V2 Trigger Execute Contract

- result: `CONTRACT_PASS`
- execute_run_id: `trigger_execute_20260529_condition_layer_20260528_source_20260528_v1`
- context_run_id: `trigger_context_snapshot_20260529_condition_layer_20260528_source_20260528_v1`
- snapshot_run_id: `realtime_snapshot_20260529_live1_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`
- event_schema_version: `v2-canonical-trigger-action-runtime`
- runner_ready: `True`

## Expected Future Writes

- TriggerMatched: `4309`
- TriggerPendingMarketData: `4552`
- TriggerStateChanged: `8861`
- common_trigger_state: `8861`
- common_trigger_match: `8861`
- common_event_outbox: `17722`

## Canonical Payload

- runtime signal_type: `B_BUY`, `S_SELL`
- trigger_mark_candidate: `normal`, `30m_volume`, `30m_shrink`
- trace fields preserve `condition_key`, `original_condition_key`, `legacy_signal_type`
- deprecated 30m and hint values are forbidden in runtime `signal_type`

## Boundary

- preflight refresh writes no database rows
- final execute requires `--execute --user-confirmed`
- N5/N6 remain blocked until N4 outbox execute is separately confirmed and passed