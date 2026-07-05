# V3 20260615 N3 -> N5 Replay Closeout

Result: `CLOSEOUT_PASS`

Goal: complete the 20260615 N3 -> N5 replay path without changing N4/N5 business rules. This closeout fixes the previous N5 `metric_missing` blocker by materializing N3 action-confirmation metrics and replaying N5 against those metrics.

## Source Lineage

- N4 source run: `n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`
- N3 action metric run: `action_confirmation_projection_metric_20260615_until_1000_from_n4_production_semantic_replay_v1`
- N5 replay run: `n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1`
- N5 consumer: `n5_action_bounded_consumer_20260615_after_n3_metric_until_1000_v1`

## N3 Source Completion

- Merged C1 subscription/control rows were written for `805/1/0/806` stock/index/board objects.
- C1 today minute refresh wrote `28175` stock 1m rows for the action-confirmation scope.
- The sole index gap, `index:BJ:899050`, had no available minute source and was not fabricated.
- Previous-day scoped preload wrote `166320` rows.

## N3 Metric Proof

- Metric materialization result: `EXECUTE_PASS`
- Metric rows: stock/index/board/total = `834/0/1/835`
- N4 `TriggerMatched` source rows = `836`
- Metric-backed valid source rows = `835`
- Explicitly excluded source event:
  - event_id: `evt_ecd61a9de061b1d3e8642091e814e6aba8b4816b`
  - asset: `index:BJ:899050`
  - source_trigger_match_id: `267216`
  - reason: `bj_identity_minute_source_unavailable`

## N5 Replay Proof

- N5 replay result: `EXECUTE_PASS`
- `common_action_run.status=passed`
- Deterministic metric join coverage: `835/835`
- `metric_missing=0`
- Action facts/events:
  - stock/index/board action facts = `834/0/1`
  - `common_action_event=835`
  - N5 outbox = `835 pending`
- Event distribution:
  - `ActionExecuted=49`
  - `ActionBlocked=786`
  - `ActionEligible=0`
  - `ActionSkipped=0`
- Blocked reasons:
  - `price_confirmation_failed=702`
  - `amount_confirmation_failed=84`
  - `metric_missing=0`

## Boundary Proof

- N4 outbox status was not updated.
- N4 source outbox remains pending:
  - `TriggerMatched=836`
  - `TriggerPendingMarketData=415`
- N5 outbox delivered/delivering = `0`.
- N6/user refs = `0`.
- sim/position refs = `0`.
- No N6 execution, no voice/mobile/sim/position/PnL/real trade.
- No old-system touch.

## Rollback Registry

- N5 rollback SQL: `sql/V3_20260615_n5_replay_after_n3_metric_rollback.sql`
- Rollback is scoped to the new N5 run and this N5 consumer's inbox/checkpoint rows for the preserved N4 source run.
- Rollback was not executed.

## Decision

N3 -> N5 is connected for the 20260615 until-1000 replay scope. The previous all-row `metric_missing` blocker is resolved. Remaining `ActionBlocked` rows are business-rule confirmation failures, not missing N3 metric coverage.

Next recommended gate:

```text
V3_20260615_N6_USER_PROJECTION_AFTER_N5_METRIC_REPLAY_CONTRACT_PREFLIGHT_GATE
```
