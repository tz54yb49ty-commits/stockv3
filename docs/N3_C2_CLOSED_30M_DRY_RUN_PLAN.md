# N3-C2 Closed Minute / Closed 30m Business Dry-Run Plan

## Summary

- result: `DESIGN_PASS`
- layer_role: `N3_market_data`
- stage: `N3-C2-business-dry-run-plan`
- generated_at: `2026-05-26`
- dry_run_only: `true`
- execute_authorized: `false`
- market_data_pull_authorized: `false`
- writes_database: `false`
- writes_outbox: `false`
- downstream_replay_authorized: `false`

This plan defines how a future C2 dry-run should inspect the current lineage and
produce a replay / closed 30m plan. It does not authorize C2 execute, market
data pulls, minute delta writes, summary writes, outbox writes, N4/N5 replay, or
workers.

## Current Lineage

```text
N2 active:
condition_layer_20260522_to_20260525_20260525102249_execute

N3 subscription:
market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

N3 B1 snapshot:
realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

N3 B2 projection:
realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute

N3 C1 today minute:
today_minute_bar_1m_20260525_until_1411__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

Candidate C2 run:

```text
closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

## Existing Inputs

- C1 today minute facts:
  - latest closed minute: `14:11`
  - rows: stock=`390213`, index=`1719`, board=`24257`, total=`416189`
  - missing objects: `9`, all BJ `920xxx`
  - outbox rows: `0`
  - `MinuteBarClosed` generated: `false`
- B2 projection facts:
  - rows: stock=`2052`, index=`9`, board=`127`, total=`2188`
  - ready rows: `2052`
  - not_ready rows: `136`, including BJ `920xxx` stock=`9`, board=`127`
  - outbox rows: `0`
- N4/N5 current-real runtime:
  - N4 projection matcher execute passed.
  - N5 current-real action execute passed.
  - C2 must not rewrite or supersede either layer.

## Dry-Run Read Strategy

The C2 dry-run must be no-pull by default. It reads only local runtime data:

```text
common_market_data_run
common_market_data_subscription
common_market_data_pull_plan
stock/index/board_minute_bar_1m
stock/index/board_closed_30m_summary
common_market_data_quality_item
common_event_outbox / inbox / checkpoint only for scoped no-write checks
```

It should not call mootdx, Tushare, TDX, or any adapter. The dry-run estimates
the future execute plan from the current C1 baseline and current subscription
objects.

## Replay Strategy

Future C2 execute should attempt a full-day 1m replay for every subscribed
object that requires `minute_bar_1m`.

The replay target is the complete 20260525 trading minute label set:

```text
09:31-11:30
13:01-15:00
240 minute labels per object
```

Object scope:

```text
stock=2052
index=9
board=127
total=2188
```

Expected full-day row capacity:

```text
2188 objects * 240 labels = 525120 rows
```

If the 9 BJ `920xxx` objects remain unavailable, the expected available rows are:

```text
2179 objects * 240 labels = 522960 rows
```

Future execute adapter routing:

```text
stock -> bars()
index -> index_bars()
board -> index_bars()
```

## Delta Strategy

C2 must not rewrite the C1 run. It writes only delta minute rows under
`c2_run_id`.

Baseline row key:

```text
asset_kind + identity_key + trade_date + bar_time
```

Delta kinds:

```text
missing_bar
changed_bar
new_bj_bar
source_missing
source_error
```

Expected main delta if source returns all non-BJ objects:

```text
C1 latest closed minute = 14:11
missing non-BJ labels = 14:12-15:00 = 49 labels
non-BJ available objects = 2179
planned main delta = 2179 * 49 = 106771 rows
```

BJ replay retry:

```text
9 objects * 240 labels = 2160 rows if source becomes available
```

Rows that already exist in C1 and match replay exactly remain untouched. Rows
that exist in C1 but differ from replay beyond tolerance are written as C2
delta rows and represented in `replay_diff_json`; C1 rows are not updated.

Future summary calculation resolves each minute label as:

```text
C2 delta row if present
else C1 baseline row
else missing
```

## Closed 30m Summary Strategy

C2 summary uses the eight official 30m buckets:

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

Each object should produce one summary row per bucket in the future execute:

```text
2188 objects * 8 buckets = 17504 summary rows
```

For each bucket:

```text
expected_minute_count = 30
actual_minute_count = count of resolved minute rows
missing_minute_count = 30 - actual_minute_count
open = first available minute open
high = max(high)
low = min(low)
close = last available minute close
volume = sum(volume)
amount = sum(amount)
source_minute_bar_ids = resolved C1/C2 minute ids
```

Status mapping:

```text
closed  = actual=30 and missing=0
partial = 1 <= actual < 30
missing = actual=0
failed  = computation/source error prevented a reliable status
```

If BJ `920xxx` remains missing, C2 still writes visible summary rows in future
execute:

```text
9 BJ objects * 8 buckets = 72 missing summary rows
```

No fake minute rows may be generated.

## Replay Diff Strategy

`replay_diff_json` should be present on summary rows and quality items. It should
include at least:

```json
{
  "c2_run_id": "closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute",
  "baseline_run_id": "today_minute_bar_1m_20260525_until_1411__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute",
  "compare_key": ["asset_kind", "identity_key", "trade_date", "bar_time"],
  "delta_kind": "missing_bar|changed_bar|new_bj_bar|source_missing|source_error",
  "tolerance": {
    "price_abs": "0.000001",
    "amount_abs": "0.01",
    "volume_abs": "0.000001"
  },
  "changed_fields": {},
  "baseline_bar_id": null,
  "c2_delta_bar_id": null
}
```

## Quality Strategy

P0 examples:

```text
lineage mismatch
c2_run_id already exists
physical table isolation violation
duplicate C2 minute keys
summary row count not equal to object_count * 8
bucket math invalid
forbidden table write detected
common_event_outbox/inbox/checkpoint rows written for c2_run_id
existing B1/B2/N4/N5 runtime changed
```

P1 examples:

```text
BJ 920xxx still unavailable after replay retry
non-BJ source gaps represented as partial/missing summaries
replay diff from C1 baseline above tolerance
summary closed_status contains partial/missing but is traceable
```

P2 examples:

```text
objects fully closed
no replay diff
all summary counts match
```

Quality item constraints must follow current `common_market_data_quality_item`
schema:

```text
layer_scope = market_data_run
data_domain in common / stock / index / board
metric meaning in table_name / gate_code / details.metric_scope
```

## Future Dry-Run Output

The future C2 dry-run runner should output:

```text
c2_run_id
source_condition_run_id
source_subscription_run_id
source_today_minute_run_ids
for_trade_date
object_count stock/index/board
expected_full_day_minute_rows
current_c1_rows
planned_delta_windows
planned_delta_row_estimate
expected_summary_rows
bucket_plan
BJ 920xxx handling
P0/P1/P2
execute_allowed=false
rollback_sql_path
```

## Boundary

This stage does not allow:

```text
C2 execute
market data pull
minute delta writes
closed summary writes
common_market_data_run writes
common_market_data_quality_item writes
common_event_outbox writes
common_event_inbox/checkpoint writes
realtime_projection_metric writes
realtime_daily_snapshot writes
N4/N5 runtime rewrite
N6/user/voice/mobile/sim/position writes
worker
```

## Next Step

Allowed next step:

```text
N3-C2 dry-run runner implementation
```

Still not allowed:

```text
N3-C2 execute
MinuteBarClosed outbox
daily close refresh
N4/N5 replay
N6 execute
worker
```
