# N5 Worker Scoped Consumption Smoke Post Review

Result: `POST_REVIEW_PASS`

This post-review was read-only. It did not execute SQL, write database rows, consume or update N4/N5 outbox/inbox/checkpoint, enter N6, or start a worker.

## Execute Proof

```text
execute_report_json_parse=PASS
status_json_parse=PASS
execute_report_result=EXECUTED
normalized_execute_result=EXECUTE_PASS
common_action_run.status=passed
P0/P1/P2=0/0/0
worker_started=false
long_running_worker_started=false
```

The first attempt hit the expected schema guard before commit: `common_action_quality_item.layer_scope` rejected `worker_scoped_consumption_smoke`. The failed transaction left no committed scoped rows. After aligning the quality scope to the existing allowed value `event_contract`, the second execute completed successfully. Live quality rows now show:

```text
event_contract=6
```

## Row Count Proof

Actual live rows match the final gate plan:

```text
common_action_run=1
common_action_quality_item=6
common_event_inbox=50
common_event_consumer_checkpoint=50
stock_action_fact=0
index_action_fact=0
board_action_fact=0
common_action_event=0
N5 common_event_outbox=0
common_position_state/event=0/0
```

## Consumption-Only Semantic Proof

```text
ActionExecuted=0
ActionBlocked=0
ActionEligible=0
ActionSkipped=0
ActionEvent/HintEvent/RiskEvent/PositionEvent=0
action_fact_rows=0
common_action_event_rows=0
N5_outbox_rows=0
action_confirmation_performed=false
semantic_action_output_generated=false
```

The runner path was `run_consumption_only_smoke_once`; it did not reuse the normal action-confirmation execute path.

## N4 Source Preservation

```text
N4 TriggerMatched pending=556
delivered/delivering=0/0
selected inbox events=50
selected source events still pending=50
N4 outbox status updated=false
N4 outbox consumed=false
common_trigger_run=1
common_trigger_state=556
common_trigger_match=556
```

Inbox/checkpoint proof:

```text
inbox rows/distinct event_id/dedup_key/partition_key=50/50/50/50
checkpoint rows/distinct partition_key/source_layer_N4_trigger=50/50/50
```

## Downstream Forbidden Proof

```text
user_projection_run=0
user_signal_projection/card/notification=0/0/0
common_event_delivery_attempt_refs=0
common_position_state/event=0/0
virtual_order/trade/position/pnl=0/0/0/0
delivery/push/voice/mobile refs=0
sim/position/pnl/real_trade refs=0
proposal/order/trade refs=0
old system touched=false
```

## Rollback Proof

Rollback SQL:

```text
sql/N5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe_rollback.sql
```

Static proof:

```text
rollback_executed=false
hard_fail_before_first_DELETE_UPDATE=true
guards_N4_N5_delivered_delivering=true
guards_N6_user_sim_order_trade_position_refs=true
preserves_N4_trigger_facts_outbox_status=true
preserves_N3_N2_N1_facts=true
no_CASCADE_DROP_TRUNCATE=true
```

## Readiness Implication

N5 worker now has scoped consumption-only smoke evidence for reading bounded N4 `TriggerMatched` outbox rows and writing scoped N5 inbox/checkpoint rows while preserving N4 outbox status.

This is not approval for:

- N5 semantic action worker
- N4 outbox delivered/delivering status update
- N5 action fact/event/outbox writes beyond existing run-once lineage
- N6 projection
- delivery/push/voice/mobile
- sim/position/pnl/real_trade
- proposal/order/trade
- long-running worker

## Decision

```text
can_mark_n5_worker_scoped_consumption_only_smoke_complete=true
recommended_next_gate=N5_WORKER_SEMANTIC_ACTION_SMOKE_READINESS_GATE
```
