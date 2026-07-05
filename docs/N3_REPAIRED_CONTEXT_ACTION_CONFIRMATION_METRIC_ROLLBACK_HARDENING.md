# N3 Repaired-Context Action-Confirmation Metric Rollback Hardening

Status: HARDENING_PASS

```text
layer_role=N3_market_data
projection_run_id=action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
rollback_sql=sql/N3_repaired_context_action_confirmation_metric_20260605_materialization_rollback.sql
business_execute=false
database_written=false
outbox_consumed=false
worker_started=false
```

## Guard Coverage

The rollback SQL hard-fails before the first DELETE when any scoped downstream reference exists.

Covered guards:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
common_trigger_match
common_action_event
user_card_projection
user_signal_projection
user_signal_card
user_notification_queue
user_sim_order
user_sim_trade
user_sim_position
n6_virtual_account
n6_virtual_order
n6_virtual_trade
n6_virtual_position
n6_virtual_position_event
n6_virtual_pnl_snapshot
downstream_layers_touched
worker_started
```

Optional N6/user/sim/virtual tables use `to_regclass('public.<table>')` before probing, so the rollback remains portable when a future or optional table is absent.

## Delete Scope

DELETE remains scoped to:

```text
stock_action_confirmation_projection_metric
index_action_confirmation_projection_metric
board_action_confirmation_projection_metric
common_market_data_quality_item
common_market_data_run
```

The rollback does not DELETE or UPDATE outbox/inbox/checkpoint, N4 TriggerMatched/outbox, N5 rows, N6/user/sim/virtual rows, N1/N2 rows, snapshot rows, minute rows, or projection source facts. It contains no CASCADE, DROP, or TRUNCATE.

## Validation

```text
rollback_static_check=passed
targeted_tests=passed
json_parse=passed
git_diff_check=passed
read_only_db_refs=0
```

Next allowed step: runtime_control may redo `N3_REPAIRED_CONTEXT_ACTION_CONFIRMATION_METRIC_EXECUTE_FINAL_GATE_REVIEW`.
