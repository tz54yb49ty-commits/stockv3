# N6 Action Projection 20260608 V13 Index-All Until 09:52 Rollback Report

- status: ROLLBACK_PASS
- generated_at: 2026-06-08T13:47:32.999688+08:00
- projection_run_id: `user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952`
- source_action_run_id: `action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- rollback_sql: `sql/N6_projection_20260608_v13_index_all_until_0952_rollback.sql`

## Deleted Rows

| table | deleted |
|---|---:|
| user_projection_run | 1 |
| user_signal_projection | 201 |
| user_signal_card | 201 |
| user_notification_queue | 0 |

## Post-Check Scoped Counts

| table | rows_after_rollback |
|---|---:|
| user_projection_run | 0 |
| user_signal_projection | 0 |
| user_signal_card | 0 |
| user_notification_queue | 0 |

## N5 Outbox Unchanged

- distribution: `[{"event_type": "ActionEligible", "status": "pending", "count": 201}]`
- expected ActionEligible pending: 201

## Forbidden Scope Proof

- N5 inbox/checkpoint refs: `{"common_event_inbox": {"exists": true, "columns_checked": ["source_run_id", "payload_json::text"], "count": 0}, "common_event_consumer_checkpoint": {"exists": true, "columns_checked": ["consumer_name", "partition_key", "source_layer", "last_event_id", "last_event_time", "last_outbox_id", "checkpoint_payload", "updated_at"], "count": 0}}`
- downstream refs: `{"user_signal_decision": 0, "user_sim_order": 0, "user_sim_trade": 0, "user_sim_position": 0, "n6_virtual_order": 0, "n6_virtual_trade": 0, "n6_virtual_position": 0, "n6_virtual_position_event": 0, "n6_virtual_pnl_snapshot": 0}`
- no worker/delivery/push/voice/mobile/sim/position/pnl/real_trade/proposal/order/trade executed.
- no N5/N4/N3/N2/N1 rollback executed.

## Rollback Static Check

- RAISE EXCEPTION line: 37
- first DELETE line: 221
- hard_fail_before_delete: true
- has_cascade: false
- has_drop: false
- has_truncate: false

## Next Gate

Allowed to return to runtime_control for N6 rollback post-review gate.
