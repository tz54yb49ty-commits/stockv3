# N4 Formal Amount Guard 20260615 Polluted Lineage Rollback Preflight

Result: `PREFLIGHT_PASS`

Reason: the 20260615 until_1000 N4 production semantic replay still contains ordinary formal `TriggerMatched` rows produced by the pre-repair snapshot amount fallback path.

## Pollution Scope

- N4 run: `n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`
- `TriggerMatched=836`
- ordinary formal snapshot fallback = `806`
- ordinary formal snapshot fallback with N5 entry = `806`
- ordinary blocked trace with N5 entry = `694`
- HINT TriggerMatched = `30`
- tainted sample: `trigger_match_id=266600`, `stock:SH:603226`

## Rollback Scope

N6:

- `v3_n6_user_projection_20260615_after_n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`
- `v3_n6_user_projection_20260615_after_n5_metric_replay_until_1000_v1`

N5:

- `n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`
- `n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1`

N4:

- `n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`

## Planned Cleanup Counts

- N6 projection/card/queue/run = `49 / 49 / 0 / 2`
- N5 outbox/action_event/action_run = `1671 / 1671 / 2`
- N5 inbox/checkpoint refs = `1671 / 1639`
- N4 outbox/match/state/run = `1251 / 836 / 1251 / 1`

## Safety

- N4 outbox delivered/delivering = `0`
- N5 outbox delivered/delivering = `0`
- N6 notification queue = `0`
- non-scoped N4 consumer refs = `0`
- non-scoped N5 runs from N4 = `0`
- non-scoped N6 runs from N5 = `0`
- rollback SQL: `sql/V3_20260615_formal_amount_guard_polluted_lineage_rollback.sql`
- hard-fail before first DELETE: true
- no DROP/TRUNCATE/CASCADE: true

Forbidden scope: N3 facts and N3 outbox status are preserved; old system, scheduler/worker, voice/mobile/sim/position/order/real trade are not touched.
