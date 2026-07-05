# N5 Worker Larger Scope Semantic Smoke Preflight

Result: `PREFLIGHT_PASS`

Generated at: `2026-06-10T19:22:10+08:00`

Layer role: `runtime_control`

This preflight is read-only. It did not execute N5, write the database, consume or update N4/N5 outbox, enter N6, or start a worker.

## Preflight Checks

```text
readiness=READINESS_PASS
contract=CONTRACT_PASS
source pending TriggerMatched=556
selected pending TriggerMatched=200
metric deterministic join coverage=200/200
target baseline rows all 0=true
stop_file_present=false
status_json_present=false
P0/P1/P2=0/0/0
```

## Expected Writes If Future Execute Is Authorized

```text
common_action_run=1
common_action_quality_item=0
stock_action_fact=56
index_action_fact=60
board_action_fact=84
common_action_event=200
N5 common_event_outbox=200
common_event_inbox=200
common_event_consumer_checkpoint=194
common_position_state=0
common_position_event=0
```

## Expected No Writes / No Side Effects

```text
N4 outbox status update=0
N5 outbox consumption/update=0
N6/user/delivery refs=0
delivery/push/voice/mobile=0
sim/position/pnl/real_trade=0
proposal/order/trade=0
old system touched=false
```

## Decision

`PREFLIGHT_PASS`. The next gate may ask the user to confirm the exact execute command. This preflight itself does not authorize execute.
