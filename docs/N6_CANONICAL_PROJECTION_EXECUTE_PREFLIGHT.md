# N6 Canonical Projection Execute Preflight Draft

Status: PREFLIGHT_DRAFT_PASS

Layer role: N6_user

Date: 2026-05-29

This is a preflight draft only. N6 execute is still disabled until a separate
final gate.

## Required Preflight Checks

Before any canonical projection execute, refresh all checks read-only:

```text
admin user exists and active
admin user_id=1
user_filter_profile default active
N6 projection schema has canonical columns and constraints
target user_projection_run_id has zero scoped rows
linked user_signal_decision rows=0
linked user_sim_* rows=0
linked voice/mobile/position refs=0
N5 outbox source run pending ActionBlocked=4309
N5 outbox ActionEligible/ActionExecuted/ActionSkipped pending=0
legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0
N5 outbox delivered/delivering=0
P0=0
```

## Current Dry-Run Baseline

```text
dry_run_result=DRY_RUN_PASS
input_events=4309
ActionBlocked=4309
planned_user_projection_run=1
planned_user_signal_projection=4309
planned_user_signal_card=4309
planned_user_notification_queue=4309
planned_user_signal_decision=0
planned_sim_rows=0
P0/P1/P2=0/5/2
```

P1 warnings are display-quality warnings only:

```text
display_basis_missing=4309
current_price_missing=4309
target_price_missing=4309
expected_return_pct_missing=4309
board_context_missing=4309
```

These warnings do not authorize backfill from N4/N3/N2 naked facts.

## Execute Blockers

Execute must BLOCK if any of the following becomes true:

```text
unsupported N5 event_type appears
BUY_HINT or SELL_HINT appears as event_type
N5 outbox counts differ from reviewed baseline without new gate
source_layer is not N5_action
required envelope fields are missing
required canonical payload fields are missing
target run scoped rows are nonzero
linked decision/sim/voice/mobile/position refs are nonzero
any write scope outside the four allowed projection tables is requested
```

## No-Write Boundary For This Gate

This preflight draft did not:

```text
write user_projection_run
write user_signal_projection
write user_signal_card
write user_notification_queue
consume N5 outbox
update N5 outbox status
write N5 inbox/checkpoint
write decision/session/watchlist/sim/position
start worker
push voice/mobile
real trade
write N1-N5
```
