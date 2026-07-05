# N5 Worker Scoped Consumption Smoke Preflight

Result: `PREFLIGHT_PASS`

```text
readiness=READINESS_PASS
runner alignment=ALIGNMENT_PASS
dry-run=DRY_RUN_PASS
contract=CONTRACT_PASS
P0/P1/P2=0/0/0
```

The aligned consumption-only runner plan is bounded to 50 pending N4 `TriggerMatched` events and writes only N5 smoke run/quality/inbox/checkpoint rows.

```text
common_action_run=1
common_action_quality_item=6
common_event_inbox=50
common_event_consumer_checkpoint=50
stock/index/board_action_fact=0/0/0
common_action_event=0
N5 common_event_outbox=0
N4 outbox update=0
```

Allowed execute command is recorded in the contract and final gate review.
