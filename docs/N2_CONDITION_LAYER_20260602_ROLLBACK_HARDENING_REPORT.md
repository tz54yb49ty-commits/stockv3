# N2 Condition Layer 20260602 Rollback Hardening Report

layer_role = N2_condition

status = FIX_PASS

## Scope

```text
target_run_id = condition_layer_20260602_source_20260602_v1
source_trade_date = 20260602
for_trade_date = 20260603
rollback_sql = sql/N2_condition_layer_20260602_rollback.sql
writes_performed = false
rollback_executed = false
condition_execute_performed = false
downstream_layers_touched = false
worker_started = false
```

## Hard-fail Guards

The rollback SQL now checks these references before the first `DELETE FROM`:

```text
common_condition_run missing guard = present
common_event_outbox refs guard = present
common_event_inbox refs guard = present
common_event_consumer_checkpoint refs guard = present
N3/N4/N5/N6 downstream refs guard = present
```

Current read-only DB proof:

```text
event_infra_refs = 0
downstream_refs = 0
```

## Delete Scope

Rollback delete scope remains limited to:

```text
stock/index/board_condition_display_basis by run_id
stock/index/board_minute_target_scope by run_id
stock/index/board_condition_pool by run_id
stock/index/board_condition_basis by run_id
stock/index/board_monitor_target by source_version = run_id
common_condition_quality_item by run_id
common_condition_run by run_id
```

Forbidden delete/update scope remains absent:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
N1 facts / active source_version
N3/N4/N5/N6 facts
worker / delivery / notification / push / voice / mobile / sim / position / real trade
```

## Verification

```text
targeted rollback hardening test = passed
rollback static proof = passed
event/downstream read-only refs proof = passed
git diff --check = passed
```

## Next Gate

```text
can_return_to_runtime_control_execute_final_gate_review = true
```
