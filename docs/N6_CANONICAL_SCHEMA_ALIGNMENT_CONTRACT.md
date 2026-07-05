# N6 Canonical Schema / Contract Alignment

Status: DRAFT_PASS

Layer role: N6_user

Date: 2026-05-29

This is a contract and migration draft gate only:

```text
migration_executed=false
database_written=false
n5_outbox_consumed=false
n5_outbox_status_updated=false
user_projection_written=false
notification_written=false
session_written=false
voice_mobile_push=false
sim_position_real_trade=false
worker_started=false
```

## Current Input Evidence

Accepted upstream N5 canonical run:

```text
action_run_id=action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
source_n4_run_id=trigger_execute_20260529_condition_layer_20260528_source_20260528_v1
N5 outbox pending=4309
ActionBlocked=4309
ActionEligible=0
ActionExecuted=0
ActionSkipped=0
legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0
N6 refs=0
position rows=0
```

The prior N6 20260525 MVP contract and runner are legacy-compatible only. They
accept `ActionEvent / HintEvent` and must not be used to execute the 20260529
canonical N5 outbox until schema, dry-run, and runner gates are aligned.

## Canonical Input Contract

N6 may consume only N5 standard action events for the canonical path:

```text
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

Legacy compatibility is preserved only for historical rows and historical MVP
replay:

```text
ActionEvent
HintEvent
```

N6 must not consume as input event types:

```text
RiskEvent
PositionEvent
BUY_HINT
SELL_HINT
TriggerMatched
TriggerPendingMarketData
TriggerStateChanged
MarketSnapshotUpdated
MinuteBarClosed
old synthetic outbox
```

`BUY_HINT / SELL_HINT` may appear only in `condition_key`,
`original_condition_key`, or trace JSON. They are displayed as provenance only
after N6 policy decides presentation; they are not N6 input event types.

N6 may still read N2 `condition_display_basis` tables as display enrichment
only. It must not directly scan N4/N5 naked fact tables to replace N5 outbox
events.

## Projection Policy Draft

Canonical N5 event interpretation for N6 MVP:

| N5 event | N5 action state | N6 card state | Candidate / trade intent | Notification policy |
|---|---|---|---|---|
| `ActionBlocked` | `blocked` | `blocked / 未确认` | not tradable, no decision, no sim | queue optional, `queued_only`, no push |
| `ActionEligible` | `eligible` | `candidate / 可关注` | visible candidate only; decision/sim still disabled until later gate | `queued_only`, no push |
| `ActionExecuted` | `executed` | `action_confirmed` | still not real trade; N6 may show confirmation only | `queued_only`, no push |
| `ActionSkipped` | `skipped` or `expired` | `skipped / expired informational` | no decision, no sim | queue optional, `queued_only`, no push |

The current 20260529 input contains only `ActionBlocked=4309`, so the first
canonical N6 dry-run should plan blocked/unconfirmed cards and queued-only
notification candidates only if policy chooses to surface them. It must not
create buy/sell decisions, sim rows, positions, voice/mobile delivery, or real
trade side effects.

## Schema Alignment Scope

Migration draft:

```text
sql/026_n6_canonical_user_projection_schema_alignment.sql
```

Rollback draft:

```text
sql/026_n6_canonical_user_projection_schema_alignment_rollback.sql
```

The draft touches only these N6-owned projection tables:

```text
user_projection_run
user_signal_projection
user_signal_card
user_notification_queue
```

It does not touch:

```text
user_account
user_session
user_filter_profile
user_watchlist
user_watchlist_item
user_signal_decision
user_sim_account
user_sim_order
user_sim_trade
user_sim_position
N1/N2/N3/N4/N5 tables
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
```

## Compatibility Changes

`user_projection_run.source_event_types` is widened to:

```text
ActionEvent
HintEvent
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

`user_signal_projection.source_event_type` is widened to the same legacy plus
canonical set.

`user_notification_queue.notification_source` is widened to keep legacy
sources and support canonical sources:

```text
n5_action_event
n5_hint_event
n5_action_eligible
n5_action_blocked
n5_action_executed
n5_action_skipped
```

Existing non-N5 queue sources are retained:

```text
index_signal
board_signal
stock_filter_signal
```

`user_signal_card.card_type` and `card_status` are widened enough to represent
blocked, confirmed, skipped, and informational user cards without introducing
voice, mobile, sim, or real trade fields.

## Canonical Trace Columns

The draft adds nullable trace columns where the 020 schema lacks canonical N5
action context:

```text
source_action_event_type
action_state
action_mark
condition_key
original_condition_key
trace_json
projection_policy
```

`user_signal_card` and `user_notification_queue` also gain nullable
`source_action_event_id` because their 020 schema had only `source_event_id`.

Existing `source_action_run_id` columns are reused and are not duplicated.

## Forbidden Scope

This alignment does not add any execution field for:

```text
voice delivery
mobile push
push provider payload
sim execution
position execution
real order
real trade
worker state
N5 outbox consumption
N5 inbox/checkpoint
```

Future N6 execute remains blocked until a new canonical dry-run, preflight, and
explicit final gate pass.

## Rollback Strategy

Schema rollback is allowed only if no canonical N6 projection values exist. If
canonical projection rows already exist, first run the reviewed business
rollback by `user_projection_run_id`.

Business rollback remains:

```text
sql/N6_projection_business_rollback.sql
```

It may delete only rows for the target run:

```text
user_notification_queue
user_signal_card
user_signal_projection
user_projection_run
```

It must block if linked `user_signal_decision` or `user_sim_*` rows exist.
Rollback must not touch N5 outbox, action facts, trigger facts, market facts,
condition facts, user accounts, sessions, voice/mobile state, or real trading
state.

## Remaining Gates

Allowed next gate:

```text
N6 canonical schema migration final gate
```

Still blocked after this draft:

```text
N6 migration execute
N6 canonical dry-run implementation
N6 canonical projection execute
N5 outbox consumption/status update
voice/mobile push
sim/position/real trade
worker
```
