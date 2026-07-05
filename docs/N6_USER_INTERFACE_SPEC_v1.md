# N6 User Interface Spec v1

Status: SPEC_FREEZE_PASS

Layer role: N6_user

Date: 2026-06-04

This document freezes the N6 standard user interface requirements. It is a
design artifact only. It does not change code, write database rows, execute
runners, consume outbox rows, start workers, or perform delivery, push, voice,
mobile, sim, position, or real trade side effects.

## 1. Purpose

N6 is the user-facing projection layer. The UI must show user-understandable
signals, cards, queues, status, lineage, and audit information derived from N6
projection tables and reviewed artifacts.

N6 UI must not recompute N3/N4/N5 facts, must not directly fetch market data,
and must not replace or reinterpret N5 market-action decisions.

## 2. Data Sources

Allowed UI data sources:

```text
user_signal_projection
user_signal_card
user_notification_queue
reviewed N4/N5/N6 report artifacts and rollback artifact paths
```

Forbidden default UI data sources:

```text
raw K-line tables
N3/N4/N5 internal fact tables as a substitute for N6 projection
user account cash/funds/position tables
sim tables
real trade tables
delivery provider tables
```

Position, sim, or real-trade data can only be added after a separate gate.

## 3. Pages

### 3.1 Dashboard

The Dashboard is the default landing page after login. It gives one-screen
runtime status without exposing raw internal tables.

Required fields:

```text
today_signal_count
ActionBlocked count
ActionExecuted count
queued_only count
pending delivery count
rollback_safe count/status
latest run_id
```

Dashboard counts must be derived from N6 projection/card/queue rows or reviewed
N6 report artifacts.

### 3.2 Signal List

Signal List is the main scan table. It must show exactly these core columns:

```text
trade_date
identity_key
asset_kind
signal_type
action_state
action_mark
blocked_reason
trigger_kind
original_condition_key
primary_trigger_period
trigger_time
queue_status
source_action_run_id
```

Required filters:

```text
trade_date
asset_kind
signal_type
action_state
blocked_reason
```

Required interaction:

```text
open Signal Detail
view lineage
export current filtered list
```

The table must not show buy/sell/order buttons by default.

### 3.3 Signal Detail

Signal Detail shows one signal with lineage and audit context.

Required sections:

```text
N4 lineage
N5 lineage
N6 lineage
run_id
event_id
rollback_safe
source artifact links
rollback SQL link
```

Lineage must be read-only and must point to reviewed run/report artifacts where
available.

### 3.4 ActionBlocked Card

Title must be:

```text
市场动作未确认
```

Forbidden wording:

```text
交易失败
```

Allowed `blocked_reason` display values:

```text
price_confirmation_failed
amount_confirmation_failed
metric_missing
metric_quality_failed
lineage_mismatch
missing_previous_session_reference
```

Forbidden user-layer reasons in ActionBlocked cards:

```text
no_position
insufficient_cash
t_plus_one_locked
already_sold
position_limit
blacklist
```

ActionBlocked means N5 did not confirm the market action. It is not a user
account failure, not a position failure, and not a trade failure.

### 3.5 ActionExecuted Card

Primary text must be:

```text
市场动作确认成立
```

ActionExecuted only means the N5 market-action confirmation fact is true.

Forbidden wording:

```text
已成交
已下单
已交易
```

ActionExecuted must not imply sim execution, real order placement, filled
trade, position mutation, cash mutation, or external delivery.

### 3.6 Notification Preview

Notification Preview displays notification queue rows in a user-readable form.

Required statuses:

```text
queued_only
preview
delivered
```

`preview` is a local UI state. It does not mean provider delivery, push, voice,
mobile delivery, or user acknowledgement.

Provider-visible payload must be sanitized. Trace, source raw payload, outbox
payload, and action-run internals must not appear in preview payload.

### 3.7 Audit Panel

Audit Panel appears from Signal Detail and from dashboard run summary.

Required fields:

```text
run_id
rollback SQL
rollback_safe
artifact links
source_action_run_id
source event_id
created_at / updated_at where available
```

Audit Panel must be read-only. It may show rollback SQL paths but must not
execute rollback.

### 3.8 Disabled Future Entrypoints

The UI may reserve disabled placeholders for:

```text
delivery
push
voice
mobile
sim
position
real trade
```

All placeholders must be visibly disabled until a separate gate authorizes the
feature.

## 4. Status Labels and Colors

Required labels:

```text
blocked
executed
eligible
skipped
queued_only
preview
delivered
rollback_safe
stale_artifact
superseded
```

Recommended color semantics:

```text
blocked: amber
executed: green
eligible: blue
skipped: gray
queued_only: slate
preview: teal
delivered: green
rollback_safe: green
stale_artifact: amber
superseded: gray
```

Colors are secondary to text. The label text must remain visible and
unambiguous.

## 5. Safety Boundary

The N6 UI is read-only by default.

Default forbidden side effects:

```text
delivery
push
voice
mobile
sim
position
real trade
N5 outbox consumption
N5 outbox status update
N5 inbox/checkpoint write
N1-N5 fact mutation
worker start
```

Every real side effect requires a separate reviewed gate.

## 6. Implementation Rules

The following rules are frozen for implementation and review:

| Rule | Requirement |
|---|---|
| N6UI-001 | N6 UI must present user-understandable signals, cards, queues, status, lineage, and audit context. |
| N6UI-002 | N6 UI must not recompute N3/N4/N5 facts, directly pull market data, or replace N5 market-action decisions. |
| N6UI-003 | N6 UI must read only N6 projection/card/queue rows and reviewed N4/N5/N6 artifacts by default. |
| N6UI-004 | Dashboard must show today signal count. |
| N6UI-005 | Dashboard must show ActionBlocked count. |
| N6UI-006 | Dashboard must show ActionExecuted count. |
| N6UI-007 | Dashboard must show queued_only count. |
| N6UI-008 | Dashboard must show pending delivery count. |
| N6UI-009 | Dashboard must show rollback_safe count or status. |
| N6UI-010 | Dashboard must show latest run_id. |
| N6UI-011 | Signal List must include trade_date, identity_key, and asset_kind. |
| N6UI-012 | Signal List must include signal_type, action_state, and action_mark. |
| N6UI-013 | Signal List must include blocked_reason. |
| N6UI-014 | Signal List must include trigger_kind, original_condition_key, primary_trigger_period, and trigger_time. |
| N6UI-015 | Signal List must include queue_status and source_action_run_id. |
| N6UI-016 | Signal List must support filters for trade_date, asset_kind, signal_type, action_state, and blocked_reason. |
| N6UI-017 | Signal List must support opening Signal Detail, viewing lineage, and exporting the current filtered list. |
| N6UI-018 | Signal Detail must show N4 lineage, N5 lineage, and N6 lineage. |
| N6UI-019 | Signal Detail must show run_id, event_id, rollback_safe, source artifacts, and rollback SQL. |
| N6UI-020 | ActionBlocked Card title must be exactly "市场动作未确认". |
| N6UI-021 | ActionBlocked Card must not use the wording "交易失败". |
| N6UI-022 | ActionBlocked Card may show only approved N5 market blocked_reason values. |
| N6UI-023 | ActionBlocked Card must not show user-layer reasons such as cash, position, T+1, already sold, limits, or blacklist. |
| N6UI-024 | ActionBlocked Card must not imply trade, sim, position, or account failure. |
| N6UI-025 | ActionExecuted Card must show "市场动作确认成立". |
| N6UI-026 | ActionExecuted Card must not use "已成交", "已下单", or "已交易". |
| N6UI-027 | ActionExecuted Card must not imply sim, real order, filled trade, position mutation, or cash mutation. |
| N6UI-028 | Notification Preview must show queued_only, preview, and delivered states. |
| N6UI-029 | Notification Preview must not imply provider delivery, push, voice, mobile, or acknowledgement unless a later gate writes that state. |
| N6UI-030 | Notification Preview must show only sanitized provider-visible payload. |
| N6UI-031 | Audit Panel must show run_id, rollback SQL, rollback_safe, artifact links, source_action_run_id, and source event_id. |
| N6UI-032 | Audit Panel must never execute rollback or mutation actions. |
| N6UI-033 | Default UI must disable delivery, push, voice, mobile, sim, position, and real trade entrypoints. |
| N6UI-034 | Any real side effect must require a separate reviewed gate. |
| N6UI-035 | Status labels must include blocked, executed, eligible, skipped, queued_only, preview, delivered, rollback_safe, stale_artifact, and superseded. |
| N6UI-036 | Status colors must reinforce text labels and must not replace readable text. |
| N6UI-037 | ActionEligible must be displayed as a watch candidate, not as a buy instruction. |
| N6UI-038 | ActionSkipped must be displayed as informational skipped/expired state, not as a system error. |
| N6UI-039 | stale_artifact must mean the displayed artifact is older than the selected or latest run context. |
| N6UI-040 | superseded must mean a run or artifact was replaced by a newer reviewed run, not deleted. |
| N6UI-041 | UI tests must assert ActionBlocked and ActionExecuted wording boundaries. |
| N6UI-042 | UI tests must assert read-only boundaries and forbidden side effects. |

## 7. Current Gaps

Current gaps before implementation:

```text
Dashboard page not implemented to this spec.
Signal List columns and filters are not normalized to this spec.
Signal Detail lineage and artifact links are not complete.
ActionBlocked/ActionExecuted wording needs explicit UI tests.
Notification Preview needs sanitized payload rendering tests.
Audit Panel needs rollback SQL and artifact link rendering.
Disabled sim/position/real trade placeholders need clear no-op behavior.
Traceability tests need to be created from N6UI-001..N6UI-042.
```

## 8. Next Gate

Allowed next step:

```text
runtime_control N6 UI spec review gate
```

Implementation remains blocked until a separate implementation gate.
