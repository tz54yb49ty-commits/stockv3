# N5 20260602 Action-Confirmation Metric Consumption Contract

- result: CONTRACT_PASS
- layer_role: N5_action
- source_n4_execute_run_id: trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- source_projection_run_id: action_confirmation_projection_metric_20260602_1105__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
- source_condition_run_id: condition_layer_20260601_source_20260601_v1
- for_trade_date: 20260602
- consumer_name: n5_action_consumer_v1
- proposed_action_run_id: action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1

## Contract Summary

N5 consumes only the allowlisted N4 action-confirmation metric source run.

| N4 event_type | N5 handling | Creates action confirmation |
|---|---|---|
| TriggerMatched | Join N3 action-confirmation metric facts by physical table and `source_action_confirmation_metric_id`; evaluate 120m / 30m / 5m / 1m rules | yes |
| TriggerPendingMarketData | quality-only / no-op / state gate | no |
| TriggerStateChanged | live/state gate only | no |

N5 no longer trusts opaque `payload.action_confirmation` as proof. If such a payload appears in a compatibility flow, it is retained only as `opaque_action_confirmation_trace_only`.

## N3 Metric Source

Metric facts are read only from:

| asset_kind | metric table |
|---|---|
| stock | stock_action_confirmation_projection_metric |
| index | index_action_confirmation_projection_metric |
| board | board_action_confirmation_projection_metric |

Live readiness for this source projection:

| table | rows |
|---|---:|
| stock_action_confirmation_projection_metric | 765 |
| index_action_confirmation_projection_metric | 54 |
| board_action_confirmation_projection_metric | 150 |

All 6 N4 `TriggerMatched` metric refs resolve to N3 metric facts: stock 2/2, index 4/4, board 0/0.

## Write-Once Grain

Action confirmation fact grain:

```text
asset_kind
identity_key
signal_type
direction
trigger_bucket / metric_minute_label
trigger_period
trigger_mark_candidate
source_action_confirmation_metric_id
```

Multiple `condition_key` values in the same grain merge into one action confirmation. Condition provenance is preserved in `trace_json.condition_provenance`.

This run has 6 `TriggerMatched` source events and 5 unique action confirmation grains. The merged grain is:

```text
stock:SZ:300382 / B_BUY / buy / 11:05 / 30m / 30m_volume / metric_id=647
condition_keys=BUY_HINT, BUY:Y,W,D
```

## Dry-Run Outcome

| item | count |
|---|---:|
| read_event_count | 5941 |
| TriggerMatched | 6 |
| TriggerPendingMarketData | 5935 |
| TriggerStateChanged | 0 |
| action_confirmation_candidates | 6 |
| unique action grains | 5 |
| quality_plan_only | 5935 |
| duplicate_action_confirmation_grain skipped | 1 |

Output event plan:

| event_type | count |
|---|---:|
| ActionExecuted | 4 |
| ActionBlocked | 1 |
| ActionEligible | 0 |
| ActionSkipped | 0 |
| legacy ActionEvent / HintEvent / RiskEvent / PositionEvent | 0 |

The four `ActionExecuted` grains are index `S_SELL` confirmations with all sell-side flags passed. The one `ActionBlocked` grain is stock `B_BUY` where N3 metric facts show `buy_120m_price_pass=false`; final `action_mark` remains null for the blocked grain.

## Boundary

This alignment is dry-run/contract only. It does not execute N5, consume N4 outbox, update inbox/checkpoint, write action facts/events/outbox, enter N6, start workers, pull market data, touch old system, or write voice/mobile/sim/position/real trade.

## Status

- runner_alignment: ready
- dry_run_passed: true
- P0/P1/P2: 0/0/0
- rollback_sql_path: sql/N5_20260602_action_confirmation_metric_execute_rollback.sql
- execute_authorized: false until a separate final gate and explicit user confirmation
