# N5 Worker Scoped Consumption Smoke Dry Run

Result: `DRY_RUN_PASS`

This artifact is read-only. It did not start a worker, execute N5, write action facts/events/outbox, consume or update N4 outbox, or enter N6.

## Source Readiness

```text
source_trigger_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
source_event_type=TriggerMatched
pending/delivered/delivering=556/0/0
distinct event_id/dedup_key/partition_key=556/556/541
runtime signal canonical B_BUY/S_SELL=556/556
invalid BUY_HINT/SELL_HINT runtime_signal_type=0
n5_entry_allowed=true=556/556
N4 action_mark emitted=0
```

## Selected Events

```text
selected_events=50
selected_events_all_pending=true
distinct event_id/dedup_key/partition_key=50/50/50
event_time range=2026-06-08 15:00:00+08:00 to 2026-06-08 15:00:00+08:00
```

## Dry-Run Plan

```text
runner_plan_result=READY
runner_allow_execute_if_user_confirms=true
runner_blockers=0
mode=consumption-only
read_event_count=50
planned_inbox_count=50
checkpoint_write_plan_count=50
```

Planned writes:

```text
common_action_run=1
common_action_quality_item=6
common_event_inbox=50
common_event_consumer_checkpoint=50
stock/index/board_action_fact=0/0/0
common_action_event=0
N5 common_event_outbox=0
```

Target baseline is clean for this smoke run/consumer: run, quality, action facts, action events, N5 outbox, inbox, and checkpoint are all `0`.
