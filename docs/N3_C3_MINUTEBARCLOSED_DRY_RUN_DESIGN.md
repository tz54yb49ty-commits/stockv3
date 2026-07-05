# N3-C3 MinuteBarClosed Dry-Run Design

## Summary

- result: `DESIGN_PASS`
- layer_role: `N3_market_data`
- stage: `N3-C3-MinuteBarClosed-dry-run-design-after-v2-contract-fix`
- generated_at: `2026-05-26`
- c3_execute_authorized: `false`
- writes_database: `false`
- writes_outbox: `false`
- consumes_outbox: `false`
- starts_worker: `false`
- enters_n4_n5_n6: `false`

This design only defines the C3 dry-run and future outbox contract. It does not
authorize C3 execute, `MinuteBarClosed` outbox writes, N4/N5 replay, N6
execution, or workers.

## Source Lineage

```text
c2_run_id =
closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_condition_run_id =
condition_layer_20260522_to_20260525_20260525102249_execute

source_subscription_run_id =
market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

Current C2 summary status:

```text
closed  = 17432
missing = 72
partial = 0
failed  = 0
```

## Dry-Run Input

C3 dry-run may read only the N3 closed 30m summary fact tables:

```text
stock_closed_30m_summary
index_closed_30m_summary
board_closed_30m_summary
```

Candidate selection:

```text
run_id = c2_run_id
closed_status = closed
```

Rows with `closed_status` in `missing`, `partial`, or `failed` are excluded
from `MinuteBarClosed` candidate generation. They remain quality / replay
evidence and must not be silently promoted into events.

## Candidate Count

Expected `MinuteBarClosed` v2 candidates:

```text
stock = 16344
index = 72
board = 1016
total = 17432
```

Expected excluded summaries:

```text
missing = 72
partial = 0
failed = 0
total = 72
```

The 72 excluded rows are the 9 BJ `920xxx` stocks across 8 closed-30m buckets.
C3 must not fabricate minute rows or emit `MinuteBarClosed` for them.

## Trace Enrichment

C3 candidate selection is based only on closed summary facts, but the future
dry-run runner may perform read-only trace enrichment from:

```text
common_market_data_subscription
common_market_data_pull_plan
```

The enrichment scope is deterministic:

```text
source_subscription_run_id
subscription_id
asset_kind
identity_key
required_data_kind = minute_bar_1m
for_trade_date = 20260525
```

Required enrichment output:

```text
subscription_id
pull_plan_id
source_adapter
data_quality_status
```

Rules:

```text
1. pull_plan_id must be resolved from control tables; no placeholder is allowed.
2. Missing subscription_id, pull_plan_id, source_adapter, source_minute_refs, or
   data_quality_status is a C3 quality blocker for that summary row.
3. Blocked rows do not generate MinuteBarClosed candidates.
4. The dry-run report must count trace_enrichment_blocked rows by asset_kind
   and blocker_code.
```

## Payload V2 Contract

C3 emits only `MinuteBarClosed` with `event_schema_version=v2` in a future
execute gate.

The v2 payload must satisfy the current validator and must not require or
fabricate `minute_bar_id`.

Required payload fields:

```text
event_schema_version = v2
closed_30m_summary_id or summary_id
source_minute_bar_ids
source_minute_refs
c2_run_id
source_condition_run_id
source_subscription_run_id
source_today_minute_run_ids
bucket_id
bucket_start
bucket_end
closed_status
replay_diff_json
quality_status
subscription_id
pull_plan_id
run_id
source_adapter
data_quality_status
```

Recommended compatibility shape:

```text
closed_30m_summary_id = summary_id
summary_id = summary_id
source_minute_bar_ids = persisted C1 bar_id values when available
source_minute_refs = non-empty C1/C2 resolved minute trace references
run_id = c3_run_id
source_adapter = N3Closed30mSummaryAdapter
data_quality_status = quality_status or passed
```

`source_minute_bar_ids` may be empty only when `source_minute_refs` is non-empty
and fully auditable. Missing `source_minute_refs` is a P0 blocker for that
candidate.

## Dedup Rule

`MinuteBarClosed` v2 uses the v2 dedup helper with this stable grain:

```text
source_layer = N3_market_data
event_type = MinuteBarClosed
asset_kind
identity_key
trade_date
c2_run_id
summary_id
bucket_id
event_schema_version = v2
```

Future dry-run must compute:

```text
dedup_key
event_id
duplicate_candidate_count
duplicate_keys_sample
```

Expected `duplicate_candidate_count` for the current C2 run is `0`. Any
duplicate key is a P0 blocker for C3 execute.

## Event Type

Allowed event type:

```text
MinuteBarClosed
```

Forbidden event types:

```text
MinuteBarReplayDiffDetected
TriggerReplay
ActionReplay
```

Missing, partial, and failed summaries must not generate `MinuteBarClosed`.

## Future Outbox Plan

Future C3 execute may write only:

```text
common_market_data_run
common_market_data_quality_item
common_event_outbox
```

Expected future outbox rows if all candidates pass trace enrichment:

```text
MinuteBarClosed = 17432
```

Future C3 execute must not write or update:

```text
stock_closed_30m_summary
index_closed_30m_summary
board_closed_30m_summary
stock_minute_bar_1m
index_minute_bar_1m
board_minute_bar_1m
stock/index/board_realtime_projection_metric
stock/index/board_realtime_daily_snapshot
common_event_inbox
common_event_consumer_checkpoint
condition tables
trigger tables
action tables
user tables
voice/mobile/sim/position tables
worker or scheduler state
old system
```

## Replay Storm Guard

C3 is an N3 outbox preparation stage only.

Hard guards:

```text
1. C3 execute writes outbox only; it does not consume outbox.
2. C3 source_run_id must not be auto-consumed by generic N4/N5 workers.
3. N4/N5 replay requires an explicit C3 run_id allowlist and owning-layer
   replay contracts.
4. C3 does not supersede B1/B2/N4/N5 passed runtime.
5. Missing/partial/failed summaries remain evidence and do not emit events.
```

## Rollback

Future C3 rollback is scoped by `c3_run_id` and may delete only:

```text
common_event_outbox rows where source_run_id = c3_run_id
common_market_data_quality_item rows where run_id = c3_run_id
common_market_data_run row where run_id = c3_run_id
```

Rollback must not touch:

```text
C2 closed_30m_summary
C2 delta minute rows
B1 snapshot
B2 projection
N4 trigger runtime
N5 action runtime
N6/user runtime
```

Rollback must block if any downstream event infrastructure references the C3
run or event ids:

```text
common_event_inbox.source_run_id = c3_run_id
common_event_consumer_checkpoint checkpoint payload references c3_run_id
common_event_outbox rows for c3_run_id are delivered or delivering
```

## Dry-Run Runner Requirements

The next dry-run runner should:

```text
1. Read the three closed summary tables for c2_run_id.
2. Select only closed_status=closed.
3. Count excluded missing/partial/failed rows.
4. Perform read-only subscription / pull_plan enrichment.
5. Build sample MinuteBarClosed v2 envelopes through the N3 event factory.
6. Validate payloads with the current v2 validator.
7. Compute v2 dedup keys and event ids.
8. Count duplicate candidates.
9. Verify future allowed / forbidden write scopes.
10. Produce a no-write dry-run report and JSON.
```

Proposed report paths:

```text
docs/N3_C3_MINUTEBARCLOSED_DRY_RUN_REPORT.md
docs/N3_C3_minute_bar_closed_dry_run_report.json
```

## Quality Gates

P0 blockers:

```text
C2 run missing or not passed
summary row count does not match C2 execute report
closed candidate count != 17432
non-closed summary selected as candidate
trace enrichment missing pull_plan_id for any candidate
payload v2 validator failure
duplicate dedup_key
planned event type is not MinuteBarClosed
future write scope includes forbidden tables
existing C3 run/outbox rows for the same c3_run_id
downstream inbox/checkpoint already references c3_run_id
```

P1 warnings:

```text
BJ 920xxx missing summaries excluded = 72
trace enrichment blockers by object if any closed summary lacks control trace
```

P2 informational:

```text
candidate distribution by asset_kind
sample payloads and dedup keys
```

Current design gate:

```text
P0 = 0
P1 = 1
P2 = 0
```

## Decision

- DESIGN_PASS: `true`
- C3 dry-run runner implementation allowed: `true`
- C3 execute authorized: `false`
- N4/N5 replay authorized: `false`
- worker authorized: `false`
