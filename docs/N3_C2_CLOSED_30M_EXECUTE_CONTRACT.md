# N3-C2 Closed Minute / Closed 30m Execute Contract

## Summary

- result: `DESIGN_PASS`
- layer_role: `N3_market_data`
- stage: `N3-C2-business-execute-contract-design`
- generated_at: `2026-05-26`
- execute_authorized: `false`
- runner_exists: `true`
- runner_readiness: `ready`
- c2_execute_allowed_now: `false`
- c2_execute_allowed_reason: `awaiting_final_gate_user_confirmation`
- writes_outbox: `false`
- `MinuteBarClosed` outbox: deferred to `N3-C3`
- daily close refresh: deferred to a separate gate
- N4/N5 replay: deferred to owning layers and separate gates

This contract defines what a future C2 execute runner may do after a separate
dry-run, preflight, rollback review, and explicit user confirmation. It does not
authorize execution.

`c2_execute_allowed_now=false` means this contract has not received the final
execute gate confirmation. It does not mean the runner is missing.

## Run Identity

```text
c2_run_id =
closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

The run id binds C2 to the full current subscription run id:

```text
market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

It must not use stale or shortened lineage strings.

## Source Runs

Future execute must require all source runs to exist and be `passed`:

```text
source_condition_run_id =
condition_layer_20260522_to_20260525_20260525102249_execute

source_subscription_run_id =
market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_today_minute_run_id =
today_minute_bar_1m_20260525_until_1411__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

source_projection_run_id =
realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

The B1 snapshot and B2 projection are already part of current-real lineage, but
C2 must not update or supersede them.

## Execute Preconditions

Future execute runner must block with P0 if any condition fails:

```text
c2_run_id absent from common_market_data_run
c2_run_id rows absent from stock/index/board_minute_bar_1m
c2_run_id rows absent from stock/index/board_closed_30m_summary
c2_run_id rows absent from common_market_data_quality_item
common_event_outbox source_run_id=c2_run_id count = 0
common_event_inbox source_run_id=c2_run_id count = 0
common_event_consumer_checkpoint for c2 consumer/run count = 0
N2/N3 source lineage all passed and exactly matched
C1 baseline run passed and writes_outbox=false
B2 projection run passed and writes_outbox=false
dry-run expected summary rows reviewed
rollback SQL present
```

Future execute must require double confirmation:

```text
--execute
--user-confirmed
```

## Allowed Writes

Future C2 execute may write only:

```text
common_market_data_run
common_market_data_quality_item
stock_minute_bar_1m delta rows
index_minute_bar_1m delta rows
board_minute_bar_1m delta rows
stock_closed_30m_summary
index_closed_30m_summary
board_closed_30m_summary
```

Minute rows written by C2 must satisfy:

```text
run_id = c2_run_id
trade_date = 20260525
is_previous_day_preload = false
source_condition_run_id = current N2 active run
source_subscription_run_id trace stored in raw_json or source fields when available
```

## Forbidden Writes

Future C2 execute must not write or update:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
common_event_delivery_attempt
stock/index/board_realtime_projection_metric
stock/index/board_realtime_daily_snapshot
existing B1/B2/N4/N5 runtime rows
condition tables
trigger tables
action tables
user tables
voice/mobile/sim/position tables
external archive / Parquet
old system
worker / scheduler state
```

## Replay And Delta Contract

Future execute attempts a full-day 1m replay for every subscribed object:

```text
09:31-11:30
13:01-15:00
240 labels per object
```

C2 compares replay rows to C1 baseline by:

```text
asset_kind + identity_key + trade_date + bar_time
```

C2 writes a delta minute row only when:

```text
1. The bar is absent from the C1 baseline, or
2. The replay bar differs from C1 beyond the configured tolerance.
```

C2 never mutates C1 baseline rows. The effective minute series for summary is:

```text
C2 delta row if available
else C1 baseline row
else missing minute
```

## BJ 920xxx Contract

The 9 BJ `920xxx` stocks must be retried during full-day replay.

If source still returns no valid rows:

```text
do not fabricate minute rows
write missing closed summary rows
write P1 quality item
keep replay_diff_json visible
```

If source returns rows:

```text
write C2 delta minute rows under c2_run_id
generate summary from those rows
record quality as recovered or partial according to count
```

## Closed 30m Summary Contract

Bucket list:

```text
0931_1000
1001_1030
1031_1100
1101_1130
1301_1330
1331_1400
1401_1430
1431_1500
```

Expected summary rows:

```text
stock = 2052 * 8 = 16416
index = 9 * 8 = 72
board = 127 * 8 = 1016
total = 17504
```

For each bucket:

```text
open = first resolved minute open
high = max resolved high
low = min resolved low
close = last resolved minute close
volume = sum resolved volume
amount = sum resolved amount
expected_minute_count = 30
actual_minute_count = resolved minute count
missing_minute_count = 30 - actual_minute_count
```

Closed status:

```text
closed  = actual=30 and missing=0
partial = 1<=actual<30
missing = actual=0
failed  = source or computation failure
```

Summary trace:

```text
source_minute_bar_ids stores C1 persisted bar_id values only.
C2 delta bar_id is generated by PostgreSQL after insert and must not be
claimed before insert.
raw_json.resolved_minute_trace is required for every resolved minute and must
include source_kind, run_id, bar_id if available, c2_delta_key for C2 deltas,
identity_key, trade_date, bar_time, and minute_label.
replay_diff_json.source_minute_refs must carry the same auditable references.
```

## Replay Diff Contract

`replay_diff_json` must be deterministic and must include:

```text
c2_run_id
baseline_run_id
replay_source_adapter
compare_key
tolerance
delta_kind
baseline_bar_id
c2_delta_bar_id
source_error if any
replay_row_hash
baseline_row_hash
diff_fields
source_trade_date
source_bar_time
```

Tolerance:

```text
price_abs = 0.000001
amount_abs = 0.01
volume_abs = 0.000001
```

## Quality Contract

All C2 quality rows must comply with the existing quality schema:

```text
layer_scope = market_data_run
data_domain in common / stock / index / board
table_name = stock/index/board_minute_bar_1m or stock/index/board_closed_30m_summary
gate_code prefix = n3_c2_closed_30m_*
details.metric_scope = closed_30m_replay
details.c2_run_id = c2_run_id
```

P0 examples:

```text
lineage mismatch
duplicate delta minute keys for c2_run_id
summary row count != 17504
invalid bucket counts
forbidden writes detected
outbox/inbox/checkpoint writes for c2_run_id
B1/B2/N4/N5 runtime changed
```

P1 examples:

```text
BJ 920xxx remains missing
source gaps produce partial/missing summary rows
replay differences from C1 baseline are traceable but require downstream review
```

## Downstream Boundary

C2 is confirmation/replay evidence only.

It must not:

```text
write MinuteBarClosed
emit events
consume B1/N4/N5 outbox
mark B1/B2/N4/N5 stale
rollback B1/B2/N4/N5
rerun N4/N5
write N6/user/voice/mobile/sim/position
```

If C2 replay diff affects objects that already produced N4/N5 facts, that is a
P1/P0 review item depending on severity and must be handed to the owning layer
through a separate replay gate.

## Rollback

Business rollback is scoped by `c2_run_id`:

```text
sql/N3_C2_closed_30m_business_rollback.sql
```

Rollback deletes only:

```text
stock/index/board_closed_30m_summary rows where run_id=c2_run_id
stock/index/board_minute_bar_1m rows where run_id=c2_run_id and is_previous_day_preload=false
common_market_data_quality_item rows where run_id=c2_run_id
common_market_data_run row where run_id=c2_run_id
```

Rollback does not touch:

```text
C1 baseline rows
B1 snapshot
B2 projection
N4 trigger runtime
N5 action runtime
outbox/inbox/checkpoint
```

Rollback must block if any C2-related event infrastructure rows exist:

```text
common_event_outbox.source_run_id = c2_run_id
common_event_inbox.source_run_id = c2_run_id
common_event_consumer_checkpoint.checkpoint_payload references c2_run_id
```

## Required Runners

Needed next:

```text
C2 dry-run runner
C2 execute runner: ready
```

Keep separate:

```text
C3 MinuteBarClosed event contract / schema / runner
EOD snapshot or official daily close refresh
N4/N5 replay review
```

## Decision

- P0 blockers for this design: `0`
- execute contract design: `passed`
- C2 dry-run implementation allowed: `true`
- C2 execute allowed now: `false`
- C2 execute allowed reason: `awaiting_final_gate_user_confirmation`
