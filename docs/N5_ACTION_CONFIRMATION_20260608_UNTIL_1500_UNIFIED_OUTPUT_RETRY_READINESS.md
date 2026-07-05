# N5 20260608 Until 15:00 Unified Output Retry Readiness

- result: `READINESS_PASS`
- source_trigger_run_id: `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- metric_run_id: `action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- proposed_action_run_id: `action_consumer_execute_20260608_until_1500_unified_output_retry__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- proposed_consumer_name: `n5_action_consumer_v1_until_1500_unified_output_retry`
- P0/P1/P2: `0/1/0`

P1 is non-blocking: N3 does not mutate N4 payload `source_action_confirmation_metric_id`; the next N5 contract must explicitly bind `metric_run_id` and use deterministic join/link policy.

## N4 Input Proof

```text
N4 post-review=POST_REVIEW_PASS
common_trigger_run.status=passed
P0/P1/P2=0/0/0
common_trigger_state=556
common_trigger_match=556
N4 outbox TriggerMatched pending=556
TriggerPendingMarketData=0
TriggerStateChanged=0
delivered/delivering=0/0
N4 consumer inbox/checkpoint=2155/2155
worker_started=false
downstream_layers_touched=false
```

## Unified Payload Readiness

```text
required unified fields missing=0
condition_signal_type present=556/556
requested_periods present=556/556
triggered_period_details present=556/556
projection_30m_required present=556/556
projection_30m_flag present=556/556
projection_30m_type present=556/556
projection_period present=556/556
projection_30m_volume_up_flag present=556/556
projection_30m_shrink_down_flag present=556/556
runtime_signal_type present=556/556
event_time present=556/556
invalid signal_type=0
runtime_signal mismatch=0
action_mark emitted=0
trigger_price null=0
n5_entry_allowed invalid=0
ordinary trigger_period=30m=0
formal period contains 30m=0
HINT formal pollution=0
```

HINT payload proof:

```text
BUY_HINT event_time=116/116
SELL_HINT event_time=6/6
BUY_HINT trigger_period=30m=116/116
SELL_HINT trigger_period=30m=6/6
HINT primary_trigger_period=null=122/122
HINT triggered_periods=[]=122/122
HINT all_trigger_periods=[]=122/122
```

## Six-Family Input Scope

```text
BUY=299
SELL=135
BUY:FULL=0
SELL:FULL=0
BUY_HINT=116
SELL_HINT=6
B_BUY=415
S_SELL=141
normal/30m_volume/30m_shrink=434/116/6
```

FULL context is present, but no FULL `TriggerMatched` was emitted because no D transition occurred. N5 input remains `556 TriggerMatched` rows.

## N5 HINT Semantic Readiness

```text
spec review=REVIEW_PASS
source-condition agnostic output=true
BUY_HINT/SELL_HINT trace-only=true
runtime signal_type only B_BUY/S_SELL
runtime BUY_HINT/SELL_HINT must be P0 contract violation
HINT does not change confirmation rule
HINT does not bypass N3 metric-aware confirmation
HINT does not auto ActionEligible
HINT does not auto alert-only
canonical output only ActionExecuted/ActionBlocked/ActionEligible/ActionSkipped
HintEvent/ActionEvent/RiskEvent/PositionEvent forbidden as canonical N5 output
action_mark non-null only for ActionExecuted + executed + passed
```

The source HINT spec carries P0/P1/P2=`0/3/4`; those are non-blocking documentation/compatibility follow-ups and do not block this readiness gate.

## N3 Metric Readiness

```text
N3 metric post-review=POST_REVIEW_PASS
metric_run_id=action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
metric_run.status=passed
metric rows stock/index/board/total=412/60/84/556
metric_ready=556
metric_not_ready=0
source_run_trace_rows=556
source_trigger_match_id_rows=556
deterministic_joinable_rows=556
N4 TriggerMatched coverage=556/556
missing=0
extra=0
duplicate metric grain=0
opaque payload.action_confirmation trusted=false
```

Previous blocker cleared:

```text
n3_action_confirmation_metric_baseline_missing=false
coverage 0/556 no longer applies
```

## N5 Clean Baseline

```text
common_action_run=0
common_action_quality_item=0
stock/index/board_action_fact=0/0/0
common_action_event=0
N5 common_event_outbox=0
N5 inbox/checkpoint for planned consumer=0/0
common_position_state/event=0/0
N6 user_projection/signal/card/notification refs=0/0/0/0
position refs=0
```

## Planned N5 Scope

```text
expected readable N4 events=556
expected action input events=556 TriggerMatched
expected skipped/no-op TriggerPendingMarketData=0
expected metric-aware action candidates=556
deterministic metric join coverage target=556/556
coverage=0/556 must be P0 BLOCK
```

`ActionExecuted / ActionBlocked / ActionEligible / ActionSkipped` distribution is intentionally deferred to the N5 contract/dry-run gate and must come from N3 metric facts. `ActionEligible/pending` must not be registered as complete, and HINT condition provenance must not create a special event type or special confirmation branch.

## Rollback Requirement

Future N5 rollback must:

```text
hard-fail before DELETE/UPDATE
guard N5 outbox delivered/delivering
guard downstream N6/user/sim/position/order/trade refs
delete only scoped N5 unified output retry rows
delete scoped planned-consumer inbox/checkpoint only
preserve N4 trigger facts/outbox status
preserve N3 metric/N3/N2/N1 facts
contain no CASCADE/DROP/TRUNCATE
```

## Forbidden Scope Proof

```text
n5_execute=false
database_business_write=false
n4_outbox_update_or_consumption=false
n5_inbox_checkpoint_write=false
n6_entered=false
worker_started=false
rollback_executed=false
delivery/push/voice/mobile=false
sim/position/pnl/real_trade=false
proposal/order/trade=false
old_system_touched=false
```

## Validation

```text
JSON parse=PASS
live DB N4 input proof=PASS
unified payload scan=PASS
N5 spec review proof=PASS
N3 metric readiness proof=PASS
N5 clean baseline proof=PASS
downstream refs scan=PASS
git diff --check=PASS
```

## Next Gate

Allowed:

```text
N5_ACTION_CONFIRMATION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_CONTRACT_GATE
```
