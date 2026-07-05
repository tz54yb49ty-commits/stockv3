# V3 20260615 N6 User Projection Execute Report

Result: `EXECUTE_PASS`

Runner result: `PROJECTION_PASS_ZERO_USER_MESSAGES`

Layer role: `N6_user`

## Executed Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_n6_projection_once.py \
  --projection-run-id v3_n6_user_projection_20260615_after_n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000 \
  --source-action-run-id n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000 \
  --contract-json-path docs/V3_20260615_N6_USER_PROJECTION_CONTRACT.json \
  --preflight-json-path docs/V3_20260615_N6_USER_PROJECTION_PREFLIGHT.json \
  --expected-n5-outbox-count ActionBlocked:pending=836 \
  --execute --user-confirmed --json \
  > docs/V3_20260615_N6_USER_PROJECTION_EXECUTE_REPORT.json
```

CLI exit code: `0`

## Execute Proof

```text
result=PROJECTION_PASS_ZERO_USER_MESSAGES
preflight_result=PREFLIGHT_PASS
P0/P1/P2=0/5/2
n5_outbox_unchanged=true
```

Write summary:

```text
committed=true
write_tables=user_projection_run
user_projection_run=1
user_signal_projection=0
user_signal_card=0
user_notification_queue=0
allowed_write_tables_only=true
```

## Live DB Proof

Target database:

```text
database=ashare_v3
user=ashare_v3_user
host=127.0.0.1
port=5432
```

Scoped N6 rows:

```text
user_projection_run=1
user_signal_projection=0
user_signal_card=0
user_notification_queue=0
```

Projection run row:

```text
status=passed
source_action_run_id=n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000
input_event_count=836
output_projection_count=0
P0/P1/P2=0/5/2
```

## Zero User Message Proof

User message filter:

```text
include_event_types=ActionEligible,ActionExecuted
```

Source / eligible summary:

```text
source_event_count=836
source_by_event_type.ActionBlocked=836
eligible_user_message_count=0
diagnosis_only_count=836
eligible_by_event_type={}
```

## N5 Outbox Unchanged Proof

```text
before: ActionBlocked:pending=836
after:  ActionBlocked:pending=836
delivered=0
delivering=0
```

No N5 outbox consume/update was performed.

## Downstream / Forbidden Scope Proof

Downstream refs:

```text
user_signal_decision=0
user_sim_order=0
user_sim_trade=0
user_sim_position=0
```

Forbidden scope:

```text
user_signal_projection/card/notification_queue writes=0
N5 outbox consume/update=false
N5 inbox/checkpoint write=false
worker start=false
delivery/push/voice/mobile=false
sim/position/PnL/real trade=false
proposal/order/trade=false
old system touch=false
```

## Rollback Proof

Rollback SQL:

```text
sql/V3_20260615_N6_USER_PROJECTION_ROLLBACK.sql
```

Static proof:

```text
hard_fail_before_first_dml=true
DROP=false
CASCADE=false
TRUNCATE=false
common_event_outbox DML=false
```

Rollback SQL was not executed.

