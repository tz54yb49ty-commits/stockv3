# N3 Lineage Refresh For N2 20260615 V2 Readiness

- result: `READINESS_PASS`
- layer_role: `N3_market_data`
- mode: `readiness_only_no_execute`
- source_trade_date / for_trade_date: `20260615` / `20260616`
- old_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v1`
- new_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v2`
- P0/P1/P2: `0/2/0`

## Prerequisite Proof

- N2 v2 post-review: `POST_REVIEW_PASS`
- v2 DB status: `passed_active`
- v1 DB status: `superseded`
- active N2 run count for 20260615 -> 20260616: `1`

## Old Lineage Proof

- old N3 subscription run: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- old subscription source_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v1`
- old N3-A1 preload run: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- old A1 source_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v1`
- old v1 artifacts remain registered evidence and must not be silently mutated.

## New N2 V2 Source Readiness

- v2 minute_target_scope rows stock/index/board: `4194/183/307`
- v2 minute_target_scope objects stock/index/board: `1822/83/127`
- expected scope rows stock/index/board: `4194/183/307`

## Proposed N3 Refresh Scope

- new subscription run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2`
- new A1 preload run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2`
- refresh target: new v2 scoped N3 subscription control rows and N3-A1 previous-day minute preload lineage.
- old v1 subscription/preload rows are preserved and excluded from rollback scope.
- target v2 baseline rows are all zero for run/quality/subscription/control/preload facts.

## Safety Requirements

- No N3 execute in this gate.
- No DB write in this gate.
- No outbox/inbox/checkpoint consume or update.
- No N4/N5/N6.
- No worker/scheduler.
- No voice/mobile/sim/position/order/real trade.

## Rollback Planning

Rollback for future execute must delete only new v2 N3 refresh rows and must guard event infra, N4/N5/N6 refs, downstream flags, and worker flags. It must not touch old v1 lineage, B1/C1/metric rows from v1, N2 facts, or downstream facts.

## Forbidden Scope Proof

- new scoped outbox/inbox/checkpoint refs: `0/0/0`
- new scoped N4 trigger match/state refs: `0/0`
- new scoped N5 action refs: `0`

## Next Gate

`N3_LINEAGE_REFRESH_FOR_N2_20260615_V2_CONTRACT_GATE`
