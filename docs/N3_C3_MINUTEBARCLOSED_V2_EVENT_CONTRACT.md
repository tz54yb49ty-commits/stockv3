# N3-C3 MinuteBarClosed v2 Event Contract

## Summary

- result: `DESIGN_PASS`
- layer_role: `N3_market_data`
- stage: `N3-C3-MinuteBarClosed-v2-event-contract-fix`
- writes_database: `false`
- writes_outbox: `false`
- consumes_outbox: `false`
- downstream_replay_authorized: `false`

This document records the C3 event contract fix only. It does not authorize C3
execute, outbox writes, N4/N5 replay, N6 execution, or workers.

## Source

C3 `MinuteBarClosed` v2 candidates are sourced from:

```text
stock_closed_30m_summary
index_closed_30m_summary
board_closed_30m_summary
```

Only `closed_status=closed` rows are event candidates. `missing`, `partial`,
and `failed` rows remain quality / replay evidence and must not generate
`MinuteBarClosed`.

Current C2 lineage:

```text
c2_run_id =
closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

Expected C3 candidate count from current C2:

```text
stock = 16344
index = 72
board = 1016
total = 17432
excluded_missing = 72
excluded_partial = 0
excluded_failed = 0
```

## Event Type

Initial C3 supports only:

```text
MinuteBarClosed
```

It must not introduce:

```text
MinuteBarReplayDiffDetected
TriggerReplay
ActionReplay
```

## Payload Contract

`MinuteBarClosed` remains backward compatible:

```text
v1: minute_bar_id
v2: closed_30m_summary_id or summary_id, plus source_minute_refs
```

Required C3 v2 payload fields:

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

`source_minute_bar_ids` may be empty when a bucket is resolved entirely from C2
delta rows, because C2 delta `bar_id` is assigned only after insert. In that
case `source_minute_refs` must carry deterministic C2 delta keys and is
required to be non-empty.

## Dedup Key

For `MinuteBarClosed` v2, the stable dedup key is:

```text
source_layer=N3_market_data
event_type=MinuteBarClosed
asset_kind
identity_key
trade_date
c2_run_id
summary_id
bucket_id
event_schema_version
```

`MinuteBarClosed` v1 keeps the existing grain:

```text
asset_kind + identity_key + trade_date + minute_bar_time + source_adapter
```

## Trace Enrichment Decision

C3 candidate selection is based only on the three closed summary tables.

For required `pull_plan_id`, C3 may perform read-only trace enrichment from:

```text
common_market_data_subscription
common_market_data_pull_plan
```

The enrichment must be deterministic and scoped to:

```text
source_subscription_run_id
subscription_id
asset_kind
identity_key
required_data_kind=minute_bar_1m
for_trade_date
```

If `pull_plan_id` cannot be resolved, the summary row becomes a C3 quality
blocker and must not generate `MinuteBarClosed`. C3 must never fabricate or
use placeholder `pull_plan_id` values.

## Replay Boundary

C3 does not replay N4/N5 and does not supersede existing passed runtime. It
only prepares or writes N3 outbox rows after a separate execute gate.

N4/N5 replay requires separate owning-layer gates:

```text
explicit C3 run_id allowlist
replay dedup
replay run_id lineage
N4 replay contract
N5 replay contract
rollback order
```

Workers must not automatically consume a C3 source run.

## Rollback

Future C3 rollback is scoped by `c3_run_id` and may delete only:

```text
common_event_outbox
common_market_data_quality_item
common_market_data_run
```

It must not touch:

```text
C2 closed_30m_summary
C2 delta minute rows
B1 snapshot
B2 projection
N4 trigger runtime
N5 action runtime
```

Rollback must block if C3 outbox was consumed or referenced by downstream
inbox/checkpoint rows.

## Decision

- validator fix required: `done`
- v2 dedup fix required: `done`
- trace enrichment decision: `allow read-only subscription/pull_plan enrichment`
- C3 execute authorized: `false`
- C3 dry-run design may be retried: `true`
