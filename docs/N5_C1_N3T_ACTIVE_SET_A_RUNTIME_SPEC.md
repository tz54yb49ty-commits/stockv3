# N5/C1/N3T Active Set A Runtime Spec

## Scope

This spec defines the Fastlane active object set A used by N5 intake, C1/N3T action-confirmation metrics, and N5 ActionExecuted.

It does not modify old N3 A1/B1/B2/N3P/N4 runtime paths, N6, schema, existing business-worker launchd labels, or canonical minute-bar tables.

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

The reference roles are distinct:

```text
episode_entry = immutable TriggerMatched that created ActionEligible
current_active_source = latest N4 event that created or refreshed the A ref
final_market_proof = matching N3T_C1_CLOSED
```

The current active source may be `TriggerStateChanged(trigger_live=true)` only
for an episode that still carries its immutable TriggerMatched entry.
TSC(true) without that entry cannot generate `ActionExecuted`.

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

N3T derives 5m/30m/120m evidence from fixed, non-overlapping trading-minute
buckets, never from rolling row counts. Each aggregate body uses the bucket's
first `open` and last `close`. Current-day source selection, previous-day
scope selection, and metric derivation share one physical calculation axis:
it starts at `09:31`, excludes physical `09:30` and `11:30`, and crosses lunch
as `11:28 -> 11:29 -> 13:00 -> 13:01`.

Previous complete-period lookup remains a distinct preload contract. It keeps
close-label ordinals `121-240`, so the previous trading day's complete
afternoon `120m` source remains available at the current-day `13:00` boundary.
Previous-day same-window amount lookup does not reuse those ordinals; it
matches the physical labels of the current fixed bucket. In particular, the
lunch-spanning 5m same-window is exactly
`11:26,11:27,11:28,11:29,13:00`. Raw labels remain in trace, and missing,
duplicate, or mixed-layout rows fail closed with a stage-specific metric-source
reason.

N3T fans object-level C1 rows out to active refs and writes only `N3T_C1_CLOSED` action-confirmation proof. N3T proof must include N5 evaluator fields and compatibility aliases:

```text
current_5m_virtual_amount
previous_5m_full_amount
current_30m_virtual_amount
previous_day_same_window_amount
```

N3T run ids and artifact paths remain source-run/ref scoped and must not collide between ordinary and B2/hint-projection rows at the same HHMM.

The scheduler hot path owns one bounded A-minute cohort per invocation. It reads
the latest explicit A snapshot once, selects at most `512` source identities and
at most `4096` object-minute proofs, then completes
`provider -> staging -> previous-day context -> metric context -> N3T writer`
without starting a second provider session. Source fetches are deduplicated by
`for_trade_date + asset_kind + identity_key`; BUY and SELL refs may share the
same market-data response while retaining independent proof/evaluation refs.
An object that was not attempted must not receive a source-only batch artifact.

The N3T existing-proof read remains proof-aware and paged. Completed proofs are
skipped before provider calls. An object without any valid proof is SLA urgent
until its first proof exists; it must not be demoted merely because its target
minute is older than the rolling three-minute window. Urgent objects are ordered
by the earliest `target close + 120 seconds` deadline with stock/index/board
round-robin fairness. Historical cursor backlog uses remaining capacity after
the urgent cohort. First-proof classification combines exact N3T proof rows for
the current candidate set with the active ref cursor contract:
`last_checked_minute_label` proves that N5 already evaluated an earlier N3T proof.
An advanced `next_unchecked_minute_label` must therefore remain backlog unless its
current target is inside the rolling live window; it must not be reclassified as
first-proof urgent merely because the earlier proof run id is outside the current
candidate set.

The invocation creates one endpoint selection/semantic probe and one thread
pool. Each worker reuses one pinned mootdx client for the cohort. Provider
concurrency is `8` below 64 source identities and `16` for 64 or more, with a
hard maximum of 16. C1/N3T Fastlane explicitly selects with
`failover_mode=active`; this invocation-local override does not change the
configured default used by other N1/N3 callers.

The endpoint circuit may open only for an exception accepted by
`is_endpoint_transport_exception()` or for three distinct required objects
returning empty data. The first recognized transport failure records the
selected endpoint once, but the in-memory incident claim and cohort abort must
be visible before endpoint health-cache persistence begins. A health-cache write
failure keeps the cohort fail-closed and records zero successful persistence
attempts; it must not reopen provider work or emit exception details. Remaining
not-yet-started objects stay eligible for immediate retry. Successful in-flight
objects remain valid; failed objects must not write synthetic source or proof. The next
five-second one-shot performs one new selection and may choose a healthy
secondary. It must not loop between endpoints inside the failed invocation.
Three distinct required-object empties are treated as one endpoint-wide
incident; one object's empty/data-quality result remains isolated.

Failure evidence is limited to `error_type`, `failure_kind`, `endpoint_id`,
`failover_mode`, and `retry_class`. It must not contain exception text, host,
port, or connection details. Endpoint transport retries bypass the 60-second
object-quality backoff. A malformed row from one object is isolated as an
object-quality failure and enters that backoff; a program failure is isolated
without retry. A required-object health-cache persistence failure is also
candidate-local: it fails only that object, is immediately retryable in the next
one-shot, and does not count as an empty result or open the endpoint circuit.
Neither candidate-local failure opens the endpoint circuit. The
distinct-three-empty endpoint-wide rule above remains the only data-result
exception.

Intraday source rows use a direction-independent atomic cache keyed by trade
date, asset kind, and identity. The first read uses
`min(256, max(32, closed_minute_ordinal + 16))`; a continuous cache uses a
32-row tail fetch and deterministic merge. Missing labels, conflicting labels,
or trade-date/scope mismatch trigger one bounded full repair with offset `256`.
If the repaired source still does not cover the pull plan, that object fails
closed.

Live objects materialize only missing closed minutes. Historical objects may
materialize up to `64` consecutive cursor minutes from the same source response.
The 30-second deadline is checked before the cohort starts; a started cohort
finishes or records object-level failures and never leaves a source-only
artifact.

Object-level data-quality failures remain fail-closed and are recorded in a compact, atomic
`n3_c1_n3t_object_cursor_retry_state_v1` artifact. The failed object/minute is deferred for 60 seconds,
then becomes eligible for another bounded attempt. A successful proof clears its retry entry. Retry
state never creates a proof, suppresses evidence, or changes the N5 confirmation contract.

Pending objects remain visible as `live` and `backlog` tiers for audit. `live`
includes both the latest three canonical closed minutes and every object still
waiting for its first valid proof. Once no urgent first-proof gap remains, the
balanced queue reserves equal capacity for live and historical backlog and
borrows unused capacity. Within each tier, stock, index, and board are consumed
round-robin, then ordered by earliest cursor, `identity_key`, and direction.

The compact manifest must report attempted and completed counts rather than treating every provider
result as an N3T proof. `c1_lane.processed_candidate_count` is the count of objects with usable source
payloads; `n3t_lane.processed_candidate_count` is the count of completed proof inputs. The manifest must
also report tier/asset selection counts, completed chunk count, and
`source_only_artifact_count=0`. Queue diagnostics include `probe_page_count`,
`existing_proof_skipped_count`, `retry_deferred_object_count`, live/backlog selected object and
candidate counts, `backlog_cursor_minutes_per_object`, and `true_remaining_candidate_count`.
It also reports `queue_mode`, `live_fastpath_attempted`,
`live_fastpath_selected_object_count`, `adaptive_live_capacity_enabled`,
`live_fastpath_chunk_count`, and `balanced_chunk_count` so fresh-close scheduling latency is auditable.
Phase metrics include `queue_census_ms`, `endpoint_selection_ms`,
`provider_fetch_ms`, `previous_day_context_ms`, `proof_build_ms`, `writer_ms`,
`artifact_write_ms`, provider offsets/connections, and the oldest proof deadline
lag. Compact object artifacts reference the source-cache path/hash and
previous-day row hash; they do not repeat full source and previous-day row
payloads.
If a cold intraday source cache fetch does not cover its pending cursor plan,
the runner performs exactly one bounded repair fetch with the maximum 256-row
offset. Incomplete or conflicting repaired data remains fail-closed.
`true_remaining_candidate_count` is exact for proof-checked pages; `proof_probe_complete=false` and
`unprobed_candidate_count` explicitly identify a bounded probe that stopped after filling its chunk.

## N5 Executed Boundary

N5 executed consumes only active A refs plus matching `N3T_C1_CLOSED` proof.

N5 executed must not consume N4 pending events, write inbox/checkpoint, update N4 outbox, or accept N3P/B1/B2/realtime metrics as final proof.

If proof is missing, N5 returns clean waiting.

If proof exists but N5 rules do not pass, N5 writes evaluation evidence only.

If proof passes, N5 writes `ActionExecuted`. The `ActionExecuted` top-level `source_trigger_event_*`, `source_n4_payload`, and trace must identify the latest N4 event that created or refreshed the active ref, while `action_entry_trigger_matched_ref` preserves the immutable TriggerMatched episode entry. For example, if `stock:SZ:301269` was refreshed by `TriggerStateChanged(trigger_live=true)` at `2026-07-06 13:52`, any later `ActionExecuted` for that active ref must use that `13:52` N4 event as its current active source rather than the older `09:55` `TriggerMatched`; the older match remains the episode entry.

### Exact-ready proof queue

The executed worker performs a complete census of the latest explicit A
snapshot before applying its write bound. It batches exact
`N3T_C1_CLOSED` proof lookup by asset table, then selects at most
`min(max_events, 256)` active refs. It must not truncate A before proof lookup
and must not build one candidate plan per ref during exact-ready discovery.
The selected refs are evaluated by one batch planner and written with the
existing canonical-key ordering, single transaction, and whole-transaction
deadlock retry.

Ready refs are ordered by the earliest `target close + 120 seconds` deadline.
Refs at the same target minute rotate through stock, index, and board; within
an asset kind, non-HINT refs precede HINT refs and `state_key` provides the
stable tie-breaker. A batch contains only one `action_run_id`; other ready runs
remain visible for the next bounded invocation.

The manifest reports `ready_census`, `selected`, `processed`, `remaining`,
`oldest_ready_age_ms`, `discovery_ms`, `planner_ms`, and `writer_ms` under
`fastlane.ready_proof_queue`. Scheduler-quiet output keeps only these scalar
values. Stale-metric re-evaluation, post-close terminalization, and the
no-exact-proof fallback remain unchanged.

## Active Worker Bootstrap Boundary

`ActionExecuted=0` is not by itself a write-activation blocker while exact-cover backlog remains. The policy review may authorize `exact_cover_backlog_bootstrap` only when active tracking, explicit A artifacts, scoped C1 artifacts, positive `N3T_C1_CLOSED` rows, and valid N3T lineage are all present.

This bootstrap authorization does not count as full-chain verification and does not weaken N5 confirmation rules. If exact-cover backlog is already zero, or any required tracking/A/C1/N3T evidence is missing or mismatched, `ActionExecuted=0` remains `n5_actionexecuted_not_advancing` and fails closed.

## 09:25 Policy Review Auto Refresh

The runtime-deferred active-worker policy review is refreshed by a separate runtime-control one-shot. It is not generated by N5 intake, C1/N3T, or N5 executed workers.

The planned label is `com.ashare-v3.n5-n3t.policy-review-refresh`, with `StartInterval=15`, `RunAtLoad=false`, and `KeepAlive=false`. Its production arguments point only to the stable activation config and do not contain a fixed exchange time or DSN argument.

All four active Fastlane LaunchAgents receive the canonical non-secret local socket conninfo through `ASHARE_V3_POSTGRES_DSN=dbname=ashare_v3 user=ashare_v3_user`. This profile contains no password, host, URI DSN, or placeholder, and removes any dependency on session-scoped `launchctl setenv`. Load-safe inactive plans do not receive database access. The stable and dated activation configs continue to contain no DSN.

The scheduler-quiet failure report may expose only allowlisted contract error codes such as `ASHARE_V3_POSTGRES_DSN_missing`. Unknown exception messages remain redacted to the exception type.

The one-shot behavior is:

```text
before 09:25                      -> silent noop
09:25 <= current time < 15:00    -> canonical read-only monitor review
existing PASS for the trade date -> silent noop; never downgrade PASS
15:00 or later                   -> silent noop
```

The review is still produced by `review_n5_n3t_fastlane_trading_day_monitor.py`. The refresher does not synthesize PASS: canonical `WAITING` and `BLOCKED` results remain unchanged. A valid candidate is written as `.tmp`, reloaded and validated for policy type, trade date, real exchange timestamp, result/readiness consistency, and secret/placeholder absence, then installed with `os.replace`.

The refresher may only perform read-only calendar, N4/N5 backlog, artifact, log, and launchd-state checks. It does not execute N5/C1/N3T business runtime, write DB/outbox/inbox/checkpoint, modify stable config, or touch N6. Installing or reloading this additional label requires a separate explicit launchd gate.

Persistent stderr logs are classified against the current trade-day session. A runtime error is current only when the stderr file mtime is not earlier than both the Shanghai trade-date midnight and the latest source mtime for that label. Older errors remain available as audit evidence but cannot block a later trade date. A current `grew_after_load` observation remains independently fail-closed.
