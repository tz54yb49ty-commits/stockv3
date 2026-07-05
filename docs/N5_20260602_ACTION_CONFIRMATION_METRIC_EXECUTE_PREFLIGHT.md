# N5 20260602 Action-Confirmation Metric Execute Preflight

- result: PREFLIGHT_PASS
- layer_role: N5_action
- source_n4_execute_run_id: trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- action_run_id: action_consumer_action_confirmation_metric_execute_20260602_1105__trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- consumer_name: n5_action_consumer_v1
- execute_authorized: false

This preflight is a readiness artifact only. Execute still requires a separate final gate and explicit user confirmation.

## Source Guard

- allowed_source_run_ids: trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
- stale/synthetic denied: 20260525 synthetic runs, 20260525 current-real projection run, 20260528 canonical run, 20260529 canonical run
- observed_source_run_ids: trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1=5941
- source_run_guard_passed: true

## N4 Outbox

| event_type | pending |
|---|---:|
| TriggerMatched | 6 |
| TriggerPendingMarketData | 5935 |
| TriggerStateChanged | 0 |

Delivered/delivering are 0/0. N5 does not update N4 outbox status.

## Planned Write Scope

If a later execute final gate is explicitly authorized, the metric-aware plan is:

| target | planned rows |
|---|---:|
| common_action_run | 1 |
| common_action_quality_item | 5935 |
| stock_action_fact | 1 |
| index_action_fact | 4 |
| board_action_fact | 0 |
| common_action_event | 5 |
| common_event_outbox | 5 |
| common_event_inbox | 5941 |
| common_event_consumer_checkpoint | 2487 |

Output event plan:

| event_type | planned rows |
|---|---:|
| ActionExecuted | 4 |
| ActionBlocked | 1 |
| ActionEligible | 0 |
| ActionSkipped | 0 |

No legacy ActionEvent / HintEvent / RiskEvent / PositionEvent output is planned.

## Metric Readiness

- source_action_confirmation_metric_id_count: 6
- metric_fact_available_count: 6
- metric_fact_missing_count: 0
- metric_status.ready: 6
- metric_quality_status.passed: 6
- all_period_confirmation_pass_count at source-event level: 4
- all_period_confirmation_failed_count at source-event level: 2
- unique action grains after merge: 5

The two failed source-event rows are the same stock buy grain and merge into one `ActionBlocked`.

## Boundary

No DB writes were performed in this preflight. N5 did not consume N4 outbox, update inbox/checkpoint, write action facts/events/outbox, enter N6, start workers, pull market data, touch old system, or write voice/mobile/sim/position/real trade.

## Rollback

- rollback_sql_path: sql/N5_20260602_action_confirmation_metric_execute_rollback.sql
- rollback_scope: action_run_id + source_trigger_run_id + consumer_name
- hard_fail_guard: true
- hard_fail_before_delete: true
- delivered_delivering_guard: true
- downstream_inbox_checkpoint_guard: true
- non_scoped_consumer_refs_guard: true
- user_voice_mobile_sim_position_refs_guard: true
- rollback_touches_N4_N3_N2_N6: false
- rollback_025_schema: false
