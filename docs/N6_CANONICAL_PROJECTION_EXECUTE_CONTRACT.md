# N6 Canonical Projection Execute Contract Draft

Status: DRAFT_PASS

Layer role: N6_user

Date: 2026-05-29

This is a contract draft only:

```text
n6_execute=false
database_written=false
n5_outbox_consumed=false
n5_outbox_status_updated=false
n5_inbox_checkpoint_written=false
worker_started=false
push_voice_mobile=false
sim_position_real_trade=false
```

## Source Gate

```text
action_run_id=action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
source_n4_run_id=trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
for_trade_date=20260529
N5 pending ActionBlocked=4309
ActionEligible=0
ActionExecuted=0
ActionSkipped=0
legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0
```

## Input Contract

N6 canonical projection execute may read only pending N5 action outbox events:

```text
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

Legacy replay compatibility remains read-only:

```text
ActionEvent
HintEvent
```

N6 must not use as input event types:

```text
BUY_HINT
SELL_HINT
RiskEvent
PositionEvent
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
MarketSnapshotUpdated
MinuteBarClosed
```

`BUY_HINT / SELL_HINT` may only appear in `condition_key`,
`original_condition_key`, or trace JSON for display provenance. They are not
N6 input event types.

The canonical runner must not scan N4/N3/N2 naked facts as event substitutes.

### Condition projection message contract

`ActionEligible` and `ActionExecuted` opt into the additive projection path only
when both markers are exact:

```text
pct_contract_version=N5-trigger-action-pct-context-v1
projection_message_contract_version=N5-n6-projection-message-v1
projection_message_contract_hash=572078a71de8cf00963f718bc812fbe3a1ae09652a3faaa8bb3774f51b882025
projection_message_status=ready
projection_message_not_ready_reasons=[]
```

N6 validates the marker, N2 context version/hash/status, asset/identity/trade
date, positive trigger/action prices and fixed-six-decimal percentage strings.
It does not recalculate N2 fields, `trigger_pct`, `action_pct`, target prices or
expected returns, and it does not query N1-N5 facts to repair a payload.

`ActionEligible` carries the frozen `trigger_price/trigger_pct`; its
`action_price/action_pct` remain null. `ActionExecuted` additionally requires
ready `action_price/action_pct`. Valid values and the full upstream context are
copied unchanged into existing projection/card JSON fields. No physical column,
DDL or schema migration is required.

An invalid marked event is an event-scoped P0: only that event's projection,
card and notification are skipped. Other valid events remain projectable, N5
outbox state is unchanged, and no upstream fact is mutated. Marker-less events
retain their read-only historical output shape and are never backfilled.

### Frozen stock industry context

For a valid marked stock event, projection generation may read only:

```text
relation=v_n6_board_membership_fact
approved_read_role=n6_ui_readonly_role
stock_identity_key=event.identity_key
trade_date=condition_projection_context.source_trade_date
board_type=tdx_industry
```

The query selects distinct `(board_identity_key, board_code, board_name)`
mappings. Exactly one distinct mapping is frozen into projection/card JSON and
the existing board columns with `industry_status=ready`. Zero mappings produce
`industry_membership_missing`; more than one produces
`industry_membership_ambiguous`. Both cases clear board fields and set
`industry_status=not_ready`, but do not invalidate the otherwise valid core
message. Index and board events use `industry_status=not_applicable`.

The following are forbidden:

```text
n6_board_membership_display_cache
n6_display_cache_run
board_membership_fact base-table reads
N1/N2 raw or base-table fallback
request-time membership lookup or repair
```

## Projection Policy

| N5 event | User card state | Notification | Decisions | Sim / real trade |
|---|---|---|---|---|
| `ActionBlocked` | `blocked / 未确认` | `queued_only`, no push | disabled | disabled |
| `ActionEligible` | `candidate / 可关注` | `queued_only`, no push | disabled until later gate | disabled |
| `ActionExecuted` | `action_confirmed` | `queued_only`, no push | disabled | disabled |
| `ActionSkipped` | `skipped / expired` | `queued_only`, no push | disabled | disabled |

Current 20260529 execute candidate therefore plans only:

```text
user_projection_run=1
user_signal_projection=4309
user_signal_card=4309
user_notification_queue=4309
user_signal_decision=0
user_sim_rows=0
```

## Future Execute Write Scope

Future execute, after a separate final gate, may write only:

```text
user_projection_run
user_signal_projection
user_signal_card
user_notification_queue
```

Every row must be scoped by `user_projection_run_id` and retain:

```text
source_action_run_id
source_event_id
source_action_event_id
source_action_event_type
action_state
action_mark
condition_key
original_condition_key
trace_json
projection_policy
```

## Forbidden Scope

Future execute remains forbidden from:

```text
N5 outbox consumption
N5 outbox status update
N5 inbox/checkpoint writes
user_signal_decision writes
user_session writes
user_watchlist writes
user_sim_* writes
voice/mobile push writes
position writes
real trade
worker start
N1-N5 writes
```

## Rollback Strategy

Business rollback must use:

```text
sql/N6_projection_business_rollback.sql
```

Rollback deletes only the target `user_projection_run_id` scope:

```text
user_notification_queue
user_signal_card
user_signal_projection
user_projection_run
```

Rollback must BLOCK if linked decision, sim, voice/mobile, position, or other
downstream references exist. It never touches N5 outbox, N5 inbox/checkpoint,
or N1-N5 facts.
