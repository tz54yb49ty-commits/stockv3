# V3 20260612 New-Plan Runtime Facts Rebuild Contract Preflight

Result: `BLOCKED`

This gate did not modify the scheduler, did not manually execute wrapper/N3/N4/N5, did not write the database, did not execute rollback, did not consume or update outbox/inbox/checkpoint, and did not enter N6/voice/mobile/sim/trade.

## Decision

Do **not** rebuild 20260612 facts/messages under the new V3 realtime plan yet.

Two hard blockers remain:

1. The live runtime DB does not yet have the realtime virtual metric fields on the N3-owned action-confirmation projection tables.
2. The prior cleanup was intentionally scoped, not a broad deletion of every 20260612 pre-new-plan runtime row. Broad 20260612 N3/N4/N5 event rows still exist and would mix old and new semantics if rebuilt now.

There is also an implementation blocker: the current `scripts/run_v3_realtime_signal_action_chain_once.py` is dry-run/report-only. It proves the plan shape, but it is not a runtime DB writer.

## Cleanup Closure

- cleanup post-review: `POST_REVIEW_PASS`
- cleanup execute: `EXECUTE_PASS`
- cleanup scope: scoped derived rows only
- source facts preserved: true
- scheduler state: `not_loaded`

The cleanup did the safe scoped reset it was designed to do. It was not a full-day wipe.

## Source Fact Proof

Live 20260612 source facts remain available:

- `stock_minute_bar_1m`: `705120`
- `index_minute_bar_1m`: `90144`
- `board_minute_bar_1m`: `56832`
- `common_market_data_subscription`: `2676`

These are the correct raw/source inputs to preserve for the new replay/rebuild path.

## Schema Blocker

Required realtime virtual metric fields are missing from all three live tables:

- `stock_action_confirmation_projection_metric`: `0/30` required fields present
- `index_action_confirmation_projection_metric`: `0/30` required fields present
- `board_action_confirmation_projection_metric`: `0/30` required fields present

Examples of missing fields:

- `realtime_metric_schema_version`
- `metric_time_label`
- `source_time`
- `observed_at`
- `snapshot_id`
- `event_id`
- `session_kind`
- `period_source`
- `is_closed_1m`
- `is_auction_virtual`
- `midday_bridge_policy`
- `current_30m_virtual_amount`
- `current_120m_virtual_amount`
- `trace_json`

The existing schema contract/preflight is ready as draft evidence:

- [V3_REALTIME_VIRTUAL_METRIC_SCHEMA_CONTRACT.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/V3_REALTIME_VIRTUAL_METRIC_SCHEMA_CONTRACT.json)
- [V3_REALTIME_VIRTUAL_METRIC_SCHEMA_PREFLIGHT.json](/Users/chuanfuchen/Documents/A股监控系统v3/docs/V3_REALTIME_VIRTUAL_METRIC_SCHEMA_PREFLIGHT.json)
- [039_v3_realtime_virtual_metric_schema_draft.sql](/Users/chuanfuchen/Documents/A股监控系统v3/sql/039_v3_realtime_virtual_metric_schema_draft.sql)

## Residual Runtime Rows

Broad 20260612 runtime event rows still exist:

- N3 `MarketSnapshotUpdated` pending: `22902`
- N4 `TriggerMatched` pending: `3249`
- N4 `TriggerPendingMarketData` pending: `1616`
- N5 `ActionBlocked` pending: `2437`

Broad text-scope row counts still seen:

- `common_event_inbox`: `10765`
- `common_event_consumer_checkpoint`: `10730`
- `common_trigger_run`: `5`
- `common_trigger_state`: `4865`
- `common_trigger_match`: `3249`
- `common_action_run`: `3`
- `common_action_event`: `2437`

Sample retained old runs include:

- `n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500`
- `n4_production_semantic_replay_20260612_market_snapshot_updated_until_1452`
- `n4_production_semantic_replay_20260612_market_snapshot_updated_until_1444`
- `n5_action_bounded_20260612_from_n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500`
- `n5_action_bounded_20260612_from_n4_production_semantic_replay_20260612_market_snapshot_updated_until_1452`

Before a full-day new-plan rebuild, choose one:

- extend cleanup with a reviewed full-day residual cleanup scope, or
- register an explicit supersession/ignore policy so new-plan reports do not read old messages as current facts.

## New-Plan Readiness

Ready:

- executable plan: `PLAN_PASS`
- schema contract: `CONTRACT_PASS`
- schema preflight: `PREFLIGHT_PASS`
- N3 realtime virtual metric builder tests: PASS
- N4/N5 business rules remain unchanged

Not ready:

- live schema migration has not been applied
- runtime DB writer for new N3 realtime virtual metrics is not yet approved/implemented
- full-day residual old runtime rows are not fully resolved

## Next Recommended Gate

`V3_REALTIME_VIRTUAL_METRIC_SCHEMA_MIGRATION_FINAL_GATE_REVIEW`

Next prompt:

```text
layer_role=runtime_control。

进入 V3_REALTIME_VIRTUAL_METRIC_SCHEMA_MIGRATION_FINAL_GATE_REVIEW。

目标：只读复核 V3 realtime virtual metric additive schema contract/preflight/rollback draft 与 live schema missing columns，确认是否允许进入 N3_market_data schema migration 用户确认点。

要求：不执行 migration、不写业务数据、不执行 wrapper/N3/N4/N5、不消费/update outbox/inbox/checkpoint、不进入 N6/voice/mobile/sim/trade。

输出：PASS/BLOCKED、live schema proof、migration command draft、rollback proof、forbidden scope proof、next prompt。
```
