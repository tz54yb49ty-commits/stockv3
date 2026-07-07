# N5/C1/N3T Active Set A Runtime Spec

## Scope

This spec defines the Fastlane active object set A used by N5 intake, C1/N3T action-confirmation metrics, and N5 ActionExecuted.

It does not modify old N3 A1/B1/B2/N3P/N4 runtime paths, N6, schema, launchd labels, or canonical minute-bar tables.

## Active Set A

A is scoped by `for_trade_date` and deduplicated at object level:

```text
asset_kind + identity_key
```

Each object row carries executable active refs. A ref is scoped by the N4 live event that created or refreshed it and must carry:

```text
source_trigger_event_id
source_trigger_event_type
source_trigger_run_id
source_trigger_event_time
trigger_time
trigger_price
triggered_periods
condition_key
projection_30m_flag
projection_30m_type
trigger_mark_candidate
source_n4_payload
```

`TriggerMatched` enters A and creates N5 `ActionEligible`.

`TriggerStateChanged(trigger_live=true)` enters or refreshes A but does not create `ActionEligible`.

`TriggerStateChanged(trigger_live=false)` removes the matching active ref from A.

`ActionExecuted` removes the matching active ref from A.

If the same object and condition receives a later `TriggerStateChanged(trigger_live=true)`, that later event refreshes the A ref. Its `trigger_time` becomes the first confirmation minute source for subsequent C1/N3T and N5 evaluation.

Each executable active ref advances by a closed-minute cursor:

```text
first_confirmation_minute_label = HH:MM from trigger_time
last_checked_minute_label = latest N5-evaluated N3T proof label
next_unchecked_minute_label = first_confirmation_minute_label when nothing has been checked,
                              otherwise the next canonical A-share C1 minute label after last_checked_minute_label
```

For example, if `trigger_time=14:01`, N3T starts at `14:01` and then advances `14:01 -> 14:02 -> ...` until either N5 writes `ActionExecuted` or N4 sends `TriggerStateChanged(trigger_live=false)`.

## Processed TSC(true) Repair

For compatibility with earlier Fastlane runs, N5 intake may rebuild A from already processed N5 inbox rows when the referenced N4 event is `TriggerStateChanged(trigger_live=true, current_status=matched)` and no executable active tracking ref exists for that event.

This repair path only creates an executable A ref in the local N5 plan/artifact. It must not create `ActionEligible`, must not update N4 outbox status, must not rewrite inbox/checkpoint rows, and must not touch N6.

If multiple processed `TriggerStateChanged(trigger_live=true)` events exist for the same object and condition, the latest event time wins. A later `TriggerStateChanged(trigger_live=false)` removes the matching ref and blocks repair of older true events.

## C1/N3T Boundary

C1 only consumes an explicit `n5_active_scope_snapshot_v1` artifact.

C1 must not scan N5 tables and must not use full-market fallback.

C1 pulls closed 1m rows for A objects only. It preserves both raw close label and physical C1 label so boundary cases such as raw `13:07` versus physical `13:06` remain auditable.

C1 may read earlier same-day and previous-day 1m rows as deterministic context for 1m/5m/30m/120m rules. Those context rows do not create pre-trigger N3T proofs for the active ref.

N3T fans object-level C1 rows out to active refs and writes only `N3T_C1_CLOSED` action-confirmation proof. N3T proof must include N5 evaluator fields and compatibility aliases:

```text
current_5m_virtual_amount
previous_5m_full_amount
current_30m_virtual_amount
previous_day_same_window_amount
```

N3T run ids and artifact paths remain source-run/ref scoped and must not collide between ordinary and B2/hint-projection rows at the same HHMM.

## N5 Executed Boundary

N5 executed consumes only active A refs plus matching `N3T_C1_CLOSED` proof.

N5 executed must not consume N4 pending events, write inbox/checkpoint, update N4 outbox, or accept N3P/B1/B2/realtime metrics as final proof.

If proof is missing, N5 returns clean waiting.

If proof exists but N5 rules do not pass, N5 writes evaluation evidence only.

If proof passes, N5 writes `ActionExecuted`. The `ActionExecuted` payload and trace must include the latest N4 event that created or refreshed the active ref. For example, if `stock:SZ:301269` was refreshed by `TriggerStateChanged(trigger_live=true)` at `2026-07-06 13:52`, any later `ActionExecuted` for that active ref must reference that `13:52` N4 event rather than an older `09:55` `TriggerMatched`.
