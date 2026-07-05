# N4 C3 MinuteBarClosed Replay Dry-Run Design

## Summary

- result: `DESIGN_PASS`
- layer_role: `N4_trigger`
- stage: `N4-C3-replay-dry-run-design`
- design_version: `n4.c3_replay_dry_run.v1`
- for_trade_date: `20260525`
- allowed_next_gate: `N4 C3 replay dry-run runner implementation`
- execute_allowed: `false`
- worker_allowed: `false`

This document defines only the N4 dry-run design for C3 `MinuteBarClosed`
confirmation / replay. It does not implement a runner, does not consume C3
outbox, does not write inbox / checkpoint / trigger facts / N4 outbox, and does
not enter N5/N6.

## Current Lineage

Current C3 allowlist run:

```text
minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

C3 evidence from the execute report:

```text
MinuteBarClosed total = 17432
stock / index / board = 16344 / 72 / 1016
status = pending
delivered / delivering = 0
inbox = 0
checkpoint refs = 0
```

Current N4 context run:

```text
trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

Current N4 projection matcher execute run:

```text
trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
```

Current N5 action execute run:

```text
action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249
```

C3 is a closed confirmation / replay event stream. It must not supersede the
current N4 projection matcher run, and it must not automatically drive a second
N5 action run.

## Replay Input Boundary

The dry-run runner may read C3 event input only with this filter:

```text
source_layer = N3_market_data
event_type = MinuteBarClosed
source_run_id = minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525102249_execute
status = pending
event_schema_version = v2
```

The C3 run id must be passed explicitly. No wildcard, latest-run lookup, date
prefix lookup, or fallback run is allowed.

Forbidden as consumption input:

```text
B1 MarketSnapshotUpdated outbox
B2 realtime projection facts
old synthetic N4 outbox
N5 outbox
non-allowlisted C3 outbox
raw minute tables
external market adapters
old system
```

Allowed read-only comparison material:

```text
allowlisted C3 MinuteBarClosed payloads
stock/index/board_closed_30m_summary for the C3 payload summary ids
current stock/index/board_trigger_context_snapshot
current common_trigger_match / common_trigger_state for the original N4 projection execute run
B2 projection facts only as trace evidence, never as replay consumption input
```

If B2 projection facts are read, their use must be labelled `trace_only=true` in
the dry-run report and they must not change any replay classification by
themselves.

## Replay Run ID

Recommended replay run id:

```text
trigger_replay_from_c3_minute_bar_closed_20260525__c3_2ebd245a603b
```

The suffix is `sha1(c3_run_id)[0:12]`. The full C3 run id remains in
`raw_json.allowed_c3_run_id` and in every report trace. The replay run id must
not equal the N4 context run id or the original N4 projection execute run id.

Recommended consumer name for future execute:

```text
n4_c3_minute_bar_closed_replay_consumer_v1
```

The consumer name must be distinct from `n4_projection_matcher_consumer_v1`.

## Signal Scope

The dry-run compares only projection / 30m class signals:

```text
B_BUY_30M_VOL
BUY_HINT
S_SELL_30M_SHRINK
SELL_HINT
```

Ordinary `B_BUY`, `S_SELL`, `BUY:FULL`, and `SELL:FULL` remain primarily
`MarketSnapshotUpdated` driven. C3 `MinuteBarClosed` may be used for audit,
quality, or later explicit confirmation contracts, but this dry-run must not
promote ordinary BUY/SELL/FULL from C3 as a primary trigger.

## Comparison Grain

Dry-run comparison grain:

```text
asset_kind
identity_key
direction
signal_type
condition_key
trigger_period
trigger_bucket
```

`trigger_period` is `30m`. `trigger_bucket` is the C3 payload / closed summary
bucket id normalized to the same bucket key used by the current N4 projection
result where possible. If the bucket cannot be mapped, the row is classified as
`missing` with reason `bucket_mapping_missing`.

## Closed Result Derivation

N4 must not read raw minute rows or rebuild projection metrics from minutes.
Closed replay matching may use only standardized N3 closed summary values and
trace fields.

Preferred closed signal inputs:

```text
closed_30m_summary.closed_status
closed_30m_summary.quality_status
closed_30m_summary.open / close / amount
closed_30m_summary.raw_json.closed_market_shape_status, if present
closed_30m_summary.raw_json.price_direction_status, if present
closed_30m_summary.raw_json.amount_basis_kind, if present
closed_30m_summary.raw_json.previous_day_same_window_amount, if present
C3 payload replay_diff_json, only as trace / quality evidence
```

Formal `would_match` requires a standardized closed signal status. The accepted
closed signal mapping is:

```text
up_volume_expanding -> B_BUY_30M_VOL / BUY_HINT
down_volume_shrinking -> S_SELL_30M_SHRINK / SELL_HINT
```

If N3 closed summary does not expose `closed_market_shape_status` or equivalent
closed comparison fields sufficient to derive the two statuses above without
reading raw minute rows, the row must be classified as `not_ready` with reason
`closed_signal_status_missing`. N4 must not infer volume expansion / shrinkage
from raw minute tables or from B2 projection facts.

## Classification Strategy

Each grain produces exactly one dry-run classification:

```text
would_match
would_clear
would_change
unchanged
missing
not_ready
```

Classification rules:

```text
would_match:
  Closed C3 result matches the signal grain, and no equivalent original N4
  projection TriggerMatched exists for that grain.

would_clear:
  Original N4 projection result matched the grain, but C3 closed result is
  present, quality-usable, and explicitly does not match the signal.

would_change:
  Both original projection and C3 closed result are present, but the signal
  status, trigger bucket, quality status, amount/price trace, or source summary
  trace differs beyond the dry-run tolerance.

unchanged:
  Original projection and C3 closed result both match the same grain, same
  signal status, same normalized bucket, and compatible quality status.

missing:
  C3 input or closed summary trace is absent for a context grain that should be
  comparable, including BJ 920xxx excluded rows and payload/summary join misses.

not_ready:
  C3 input exists but cannot be used for replay comparison because required
  closed status, quality, trace, bucket mapping, or standardized closed signal
  status is missing or not usable.
```

Recommended reason codes:

```text
c3_event_missing
closed_summary_missing
closed_status_not_closed
closed_quality_not_usable
closed_signal_status_missing
bucket_mapping_missing
projection_match_missing
projection_match_present
status_changed
quality_changed
value_trace_changed
unchanged_confirmed
```

## Diff Strategy

The dry-run builds two maps:

```text
projection_result_by_grain:
  read from common_trigger_match where run_id = current N4 projection execute run

closed_result_by_grain:
  read from allowlisted C3 MinuteBarClosed payloads joined to closed_30m_summary
```

It then computes:

```text
projection matched but closed not matched:
  would_clear if closed signal is available and nonmatching;
  not_ready if closed signal cannot be derived safely;
  missing if C3/summary is absent.

projection not matched but closed matched:
  would_match.

both matched but value/quality changed:
  would_change.

both matched and compatible:
  unchanged.
```

Value comparison is evidence only in dry-run. It must include:

```text
projection_signal_status
closed_signal_status
projection_window_id
closed_bucket_id
projected_window_amount if available
closed_window_amount
projection_quality_status
closed_quality_status
source projection id / trigger_match_id
source C3 event_id / closed_30m_summary_id
period_trigger_baseline_trace
```

Dry-run must also summarize:

```text
by asset_kind
by signal_type
by classification
by reason_code
by trigger_bucket
BUY_HINT / SELL_HINT counts
not_ready counts for board and BJ 920xxx
```

## Event And Outbox Recommendation

Dry-run writes no outbox.

Initial replay execute should also avoid writing standard live `TriggerMatched`
or `TriggerPendingMarketData` outbox unless a separate replay-specific contract
is approved. Reusing standard N4 events is unsafe because N5 standard consumers
may treat them as a new live trigger stream.

If a future execute needs an outbox, prefer a replay-specific event such as:

```text
TriggerReplayDiff
```

That event is not currently part of the N4 event contract or schema. Adding it
requires a separate additive schema / event contract review and a separate N5
replay allowlist contract. This design does not expand schema.

## Dry-Run Report Contract

The future runner should write only report artifacts such as:

```text
docs/N4_C3_REPLAY_DRY_RUN_REPORT.md
docs/N4_C3_replay_dry_run_report.json
```

Required top-level report fields:

```text
result
layer_role
replay_run_id
allowed_c3_run_id
trigger_context_run_id
source_condition_run_id
source_subscription_run_id
source_c2_run_id
original_n4_projection_execute_run_id
input_event_count
classification_summary
signal_summary
asset_summary
reason_summary
sample_diffs
row_count_guard
boundary_confirmation
P0/P1/P2
```

P0 gates:

```text
C3 run id is not explicitly allowlisted
C3 outbox count/status does not match expected pending input
delivered/delivering C3 rows are present
C3 inbox/checkpoint already exists for replay consumer
current N4 context run is not passed
original N4 projection execute run is not passed
ordinary BUY/SELL/FULL classified as C3 primary trigger
old synthetic source_run_id appears in input
B1 MarketSnapshotUpdated appears in replay input
N5 outbox appears in replay input
raw minute table read is attempted
database row counts change during dry-run
```

P1 gates:

```text
closed_signal_status_missing rows are present
BJ 920xxx missing rows are visible
board rows are not_ready or cannot map to original projection bucket
value_trace_changed rows require downstream review
```

## Rollback Strategy

This dry-run has no DB rollback. Generated design or report files can be
deleted if discarded.

Future replay execute rollback, if later approved, must delete only rows scoped
by `replay_run_id` and replay consumer name:

```text
common_event_inbox
common_event_consumer_checkpoint
common_trigger_state
common_trigger_match
common_trigger_quality_item
common_event_outbox, only if future replay outbox is allowed
common_trigger_run
```

Rollback must not touch:

```text
original N4 projection matcher passed run
N5 current-real action passed run
N3 C3 outbox
B1 snapshot facts / outbox
B2 projection facts
C2 closed summary facts
C3 market data run / quality
old synthetic outbox
old system
```

If any future replay outbox has been consumed downstream, rollback must stop and
handoff to the owning downstream layer first.

## Replay Storm Guard

The dry-run and all future replay stages must enforce:

```text
no worker
no automatic N5 consumption
explicit C3 run id allowlist
distinct N4 replay consumer name
distinct replay run id
no standard live N4 outbox by default
N5 replay requires a separate allowlist contract
old synthetic source_run_id denylist
current N4/N5 passed runtime remains authoritative
```

## Boundary Confirmation

This design allows only document writes. It forbids:

```text
consume C3 outbox
write common_event_inbox
write common_event_consumer_checkpoint
write common_trigger_state
write common_trigger_match
write common_event_outbox
write action/user/voice/mobile/sim/position
start worker
pull market data
touch old system
```

## Next Gate

`DESIGN_PASS`.

Allowed next step:

```text
N4 C3 replay dry-run runner implementation
```

Still blocked:

```text
N4 C3 replay execute
N4 replay outbox emission
N5 replay consumption
N6 execution
worker
schema expansion for replay events
```
