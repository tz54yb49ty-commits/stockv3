# N6 20260603 V1 Market-Action-Confirmation Projection Post-Review Recovery

Status: POST_REVIEW_RECOVERY_PASS

Layer role: N6_user

Date: 2026-06-04

This artifact recovers the post-review record for an existing N6 shadow
projection run. The recovery gate was read-only:

```text
execute_performed_by_this_gate=false
database_write_by_this_gate=false
n5_outbox_consumed=false
n5_outbox_status_updated=false
worker_started=false
delivery_push_voice_mobile=false
sim_position_real_trade=false
```

## Inputs

```text
source_action_run_id=action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
source_trigger_run_id=trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
projection_run_id=user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
```

Reviewed artifacts:

```text
docs/N6_20260603_v1_market_action_confirmation_projection_dry_run_report.json
docs/N6_20260603_v1_market_action_confirmation_projection_contract.json
docs/N6_20260603_v1_market_action_confirmation_projection_preflight.json
sql/N6_projection_business_rollback.sql
```

## Existing Run DB Proof

```text
user_projection_run.status=passed
input_event_count=863
output_projection_count=863
P0/P1/P2=0/5/2
source_event_types=[ActionBlocked]
```

Run-scoped rows:

```text
user_projection_run=1
user_signal_projection=863
user_signal_card=863
user_notification_queue=863
```

Card / queue distribution:

```text
card_status=blocked / source_action_event_type=ActionBlocked / action_state=blocked / count=863
notification_source=n5_action_blocked / queue_status=queued_only / channel=broadcast_queue / count=863
```

`queued_only` rows are N6 projection queue rows only. They are not provider
delivery, push, voice/mobile, sim, position, or real trade.

## N5 Outbox Proof

N5 source run remains unchanged for N6 consumption purposes:

```text
common_action_run.status=passed
N5 P0/P1/P2=0/0/0
action_fact_row_count=863
action_fact_distribution stock/index/board=680/34/149
common_action_event ActionBlocked=863
common_event_outbox ActionBlocked:pending=863
delivered/delivering=0/0
distinct_event_ids=863
```

The persisted `user_projection_run.source_n5_outbox_range` also records:

```text
outbox_consumed=false
outbox_status_updated=false
event_type_counts.ActionBlocked=863
```

## Boundary Proof

Fresh DB probes:

```text
N6 inbox refs for source_run=0
N6 checkpoint refs for N5_action=0
user_signal_decision=0
user_watchlist=0
user_watchlist_item=0
linked user_sim_order/trade/position=0/0/0
common_position_state=0
common_position_event=0
voice/mobile/delivery optional tables=absent
```

`user_sim_account` total rows are 3 existing rows and are not linked to this
projection run; no sim order/trade/position rows exist for this run.

## Rollback Summary

Rollback SQL:

```text
sql/N6_projection_business_rollback.sql
```

Rollback scope:

```text
user_projection_run_id=user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
```

Delete order:

```text
user_notification_queue
user_signal_card
user_signal_projection
user_projection_run
```

Hard-fail guard before the first `DELETE` covers linked decision, sim, voice,
mobile, and position refs. Optional future voice/mobile/position tables use
`to_regclass` checks. Rollback does not touch N5 outbox, N5 inbox/checkpoint,
or N1-N5 facts.

## Next Gate

Allowed next gate:

```text
runtime_control registration of N6 shadow projection passed
```

