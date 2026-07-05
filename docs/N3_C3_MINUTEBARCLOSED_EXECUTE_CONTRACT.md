# N3-C3 MinuteBarClosed Outbox Execute Contract

## Summary

- result: `CONTRACT_READY`
- layer_role: `N3_market_data`
- execution_mode: `minute_bar_closed_outbox_run_once_execute`
- c3_run_id: `minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- c2_run_id: `closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`
- common_market_data_run source_trade_date: `20260525`
- common_market_data_run prev_trade_date: `20260525`
- event_type: `MinuteBarClosed`
- event_schema_version: `v2`
- writes_outbox: `true`
- consumes_outbox: `false`
- c3_execute_authorized: `false`
- runner_exists: `true`
- runner_readiness: `ready`

`c3_execute_authorized=false` means C3 is waiting for the final user execute gate. It does not mean the runner is missing.

## Source Lineage

- source_condition_run_id: `condition_layer_20260522_to_20260525_20260525102249_execute`
- source_subscription_run_id: `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- source_c2_run_id: `closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- previous_day_minute_date: `20260522`
- source_previous_day_minute_run_id: `previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`

C3 is a `20260525` closed-event publication run. To satisfy the existing `common_market_data_run` CHECK constraint, `source_trade_date` and `prev_trade_date` both use `20260525`; previous-day minute provenance remains in payload / quality details / run `raw_json.previous_day_provenance`.

## Expected Output

- MinuteBarClosed total: `17432`
- stock: `16344`
- index: `72`
- board: `1016`
- excluded missing: `72`
- excluded partial: `0`
- excluded failed: `0`
- BJ 920xxx excluded summary rows: `72`
- duplicate candidate count: `0`
- payload invalid count: `0`
- trace blockers: `0`
- P0/P1/P2: `0/1/0`

Only `closed_status=closed` C2 summaries generate `MinuteBarClosed`. Missing, partial, and failed summaries do not generate outbox rows.

## Write Scope

Allowed execute writes:

```text
common_market_data_run
common_market_data_quality_item
common_event_outbox
```

Forbidden writes:

```text
stock_closed_30m_summary
index_closed_30m_summary
board_closed_30m_summary
stock_minute_bar_1m
index_minute_bar_1m
board_minute_bar_1m
stock_realtime_projection_metric
index_realtime_projection_metric
board_realtime_projection_metric
stock_realtime_daily_snapshot
index_realtime_daily_snapshot
board_realtime_daily_snapshot
common_event_inbox
common_event_consumer_checkpoint
common_event_delivery_attempt
condition tables
trigger/action/user/voice/mobile/sim/position tables
N4/N5/N6
worker
old system
```

## Payload Contract

MinuteBarClosed v2 must validate without `minute_bar_id`. Payload requires:

```text
closed_30m_summary_id / summary_id
source_minute_bar_ids
source_minute_refs
c2_run_id
source_condition_run_id
source_subscription_run_id
source_today_minute_run_ids
bucket_id
bucket_start / bucket_end
closed_status
replay_diff_json
quality_status
subscription_id
pull_plan_id
run_id
source_adapter
data_quality_status
```

`pull_plan_id` must be enriched by read-only subscription / pull_plan trace. Placeholder `pull_plan_id` is forbidden.

## Replay Guard

- C3 writes pending outbox only.
- C3 does not consume outbox.
- C3 does not write inbox/checkpoint.
- N4/N5 replay requires an explicit `c3_run_id` allowlist and separate owning-layer contracts.
- Worker auto-consumption of this `c3_run_id` is forbidden.

## Rollback

Rollback may delete only:

```text
common_event_outbox
common_market_data_quality_item
common_market_data_run
```

Rollback must block if C3 outbox is delivered/delivering, if inbox rows exist, or if checkpoint rows reference this `c3_run_id`.
