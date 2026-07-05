# V3 20260615 N5 Replay Contract

Result: `DRY_RUN_PREFLIGHT_PASS`

## Scope

- source_trigger_run_id: `n4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_v1`
- action_run_id: `v3_n5_action_replay_20260615_after_n4_repaired_formal_price_amount_chain_and_n3_coverage_repair_v1`
- consumer_name: `n5_action_consumer_v1`
- source_metric_run_id: `action_confirmation_projection_metric_20260615_repaired_formal_price_amount_chain_coverage_repair_v1__n4_20260615_repaired_formal_price_amount_chain_replay_v1`
- execute_authorized: `False`

## Source N4 Proof

- TriggerMatched pending: `1029`
- TriggerPendingMarketData pending: `3696`
- TriggerStateChanged pending: `0`
- delivered/delivering: `0/0`

## N5 Planned Distribution

- planned_action_fact_count: `1029`
- stock/index/board action facts: `910/51/68`
- output events: `{'ActionEligible': 0, 'ActionBlocked': 961, 'ActionExecuted': 68, 'ActionSkipped': 0}`
- quality_plan_only_count: `3696`

## Metric Join Proof

- metric facts available: `1029/1029`
- metric missing: `0`
- all-period pass/fail: `68/961`

## Pending Non-Entry Proof

- TriggerPendingMarketData rows: `3696`
- pending_action_fact_plan_count: `0`

## Rollback

- rollback_sql_path: `sql/V3_20260615_n5_replay_after_n4_repaired_formal_price_amount_chain_and_n3_coverage_repair_rollback.sql`
- hard-fail before first DELETE: `true`
- preserves N4/N3 facts and outbox status: `true`

## Forbidden Scope

- N5 execute / DB business writes / N4 outbox consumption / N6 / worker / voice/mobile/sim/position/order/real trade: `false`
