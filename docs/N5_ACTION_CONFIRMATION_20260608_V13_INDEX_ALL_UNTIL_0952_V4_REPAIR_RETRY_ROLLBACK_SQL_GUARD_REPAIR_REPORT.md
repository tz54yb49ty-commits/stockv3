# N5 Action Confirmation 20260608 v13 Index-All Until 09:52 v4 Repair Retry Rollback SQL Guard Repair Report

Result: **REPAIR_PASS**

This runtime_control gate updated the rollback SQL guard and generated this repair report. It did not execute rollback SQL, did not write the business database, did not run metric-aware N5, did not consume or update outbox/inbox/checkpoint, did not start a worker, and did not touch the old system.

## Root Cause

The previous rollback attempt was blocked before the first DELETE:

```text
N5 rollback blocked: non-target N5 table common_event_outbox references source run (3920)
```

Root cause:

```text
common_event_outbox was included in the generic non-target N5 table scan.
That scan matched preserved N4_trigger source outbox rows by source_trigger_run_id.
Preserved N4_trigger source outbox rows=3920.
```

Those N4 rows must be preserved. N5 rollback must not block simply because the upstream N4 source outbox exists.

## SQL Repair Summary

Updated file:

```text
sql/N5_action_confirmation_20260608_v13_index_all_until_0952_v4_repair_retry_rollback.sql
```

Repair:

```text
generic non-target scan no longer includes common_event_outbox
explicit non-target N5_action outbox guard added
new guard scope:
  common_event_outbox
  where source_layer='N5_action'
    and source_run_id <> target action_run_id
    and row references source_trigger_run_id
```

Preserved:

```text
N4_trigger source outbox rows
N4 trigger facts
N3 metric / N3 / N2 / N1 facts
```

## Guard Proof

```text
hard-fail before first DELETE/UPDATE=true
guards scoped N5 outbox delivered/delivering=true
guards downstream refs to N5 outbox/action_run_id=true
guards non-scoped N5 refs to source_trigger_run_id=true
guards non-scoped consumers of N4 outbox=true
guards N6/user/sim/position/order/trade refs=true
root-cause guard no longer counts preserved N4_trigger common_event_outbox rows=true
no CASCADE/DROP/TRUNCATE=true
```

## Delete Scope Proof

Rollback delete scope remains scoped to N5 retry rows only:

```text
common_event_consumer_checkpoint for n5_action_consumer_v1 / source N4 run
common_event_inbox for n5_action_consumer_v1 / source N4 run
common_event_outbox where source_layer='N5_action' and source_run_id=target action run
common_action_event where run_id=target action run
board_action_fact where run_id=target action run
index_action_fact where run_id=target action run
stock_action_fact where run_id=target action run
common_action_quality_item where run_id=target action run
common_action_run where run_id=target action run
```

## Live Readiness Proof

N5 target rows are still present:

```text
common_action_run=1
common_action_quality_item=3801
stock/index/board_action_fact=113/6/0
common_action_event=119
N5 common_event_outbox=119
N5 common_event_inbox=3920
N5 consumer checkpoint=1997
ActionEligible pending=119
delivered/delivering=0/0
```

N4 is preserved:

```text
TriggerMatched pending=119
TriggerPendingMarketData pending=3801
N4 source outbox total=3920
common_trigger_match=119
common_trigger_state=3920
```

N3 metric is preserved:

```text
stock/index/board metric=113/6/0
total metric=119
```

Downstream refs remain zero:

```text
user_projection_run=0
user_signal_projection=0
user_signal_card=0
user_notification_queue=0
user_signal_decision=0
common_position_state/event=0/0
user_sim_order/trade/position=0/0/0
common_event_delivery_attempt=0
virtual_order/trade/position/pnl=0/0/0/0
```

The repaired guard no longer counts preserved N4 outbox rows:

```text
preserved N4 outbox rows=3920
non-target N5_action outbox refs to source_trigger_run_id=0
```

## Forbidden Scope Proof

```text
rollback_executed=false
database_written=false
metric_aware_n5_rerun_executed=false
N4 rollback executed=false
N3 rollback executed=false
N4/N5 outbox/inbox/checkpoint consumed or updated=false
worker_started=false
entered_N6=false
delivery/push/voice/mobile=false
sim/position/pnl/real_trade=false
proposal/order/trade=false
old_system_touched=false
```

## Decision

Allow re-entering:

```text
N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_ROLLBACK_FINAL_GATE_REVIEW_FOR_METRIC_AWARE_RERUN
```

Metric-aware N5 rerun remains blocked until rollback final gate review passes and the scoped N5 eligibility-only rollback succeeds, unless a separate supersede policy is explicitly approved.
