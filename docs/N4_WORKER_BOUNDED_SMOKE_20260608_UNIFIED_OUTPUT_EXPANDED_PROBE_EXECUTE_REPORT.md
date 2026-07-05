# N4 Worker Bounded Smoke Expanded Probe Execute Report

Result: `EXECUTE_PASS`

## Execute Proof

- smoke_run_id: `n4_worker_bounded_smoke_20260608_unified_output_expanded_probe`
- consumer_name: `n4_trigger_worker_v1_bounded_smoke_expanded_probe`
- bounded_smoke_only: `true`
- worker_started: `false`
- long_running_worker_started: `false`
- P0/P1/P2: `0/1/0`
- P1 warning: `projection_trace absent / consumption-only scope`

## Row Count Proof

- common_trigger_run: `1`
- common_trigger_quality_item: `2`
- common_event_inbox: `50`
- common_event_consumer_checkpoint: `50`
- common_trigger_state: `0`
- common_trigger_match: `0`
- common_event_outbox: `0`

## Source Boundary Proof

- N3 MarketSnapshotUpdated pending: `2155`
- N3 delivered/delivering: `0/0`
- selected source events pending: `50`
- selected source events not pending: `0`
- N3 outbox locked/updated/consumed: `false`
- N3 facts changed: `false`

## N4 Semantic Proof

- TriggerMatched emitted: `0`
- TriggerPendingMarketData emitted: `0`
- TriggerStateChanged emitted: `0`
- common_trigger_match writes: `0`
- N5 entry count: `0`

## Downstream Forbidden Proof

- N5 common_action_run refs: `0`
- N5 common_action_quality_item refs: `0`
- N5 common_action_event refs: `0`
- stock/index/board action fact refs: `0`
- N6/user refs: `0`
- delivery/push/voice/mobile: `false`
- sim/position/pnl/real_trade: `false`
- proposal/order/trade: `false`
- old system touched: `false`

## Rollback Proof

- rollback_sql: `sql/N4_worker_bounded_smoke_20260608_unified_output_expanded_probe_rollback.sql`
- rollback_executed: `false`
- hard_fail_before_DELETE_UPDATE: `true`
- guards_downstream_refs: `true`
- delete_scope_only_scoped_smoke_rows: `true`
- no_CASCADE_DROP_TRUNCATE: `true`

## Next Gate

`N4_WORKER_BOUNDED_SMOKE_EXPANDED_SCOPE_POST_REVIEW_GATE`
