# N3 20260617 Full-Day Current Minute Missing BJ Index Policy Gate

- result: `POLICY_GATE_PASS`
- chosen_path: `quality_visible_blocker_plus_excluding_blocker_scoped_c1`
- C1 backfill executed: `false`
- B2 metric executed: `false`
- N4/N5/N6 entered: `false`

## Chosen Path Proof

Alternate minute source was not selected. The implemented N3 current-minute path is `MootdxTodayMinuteAdapter` / mootdx scoped closed-minute expansion, and the prior source acquisition probe returned `0` rows for both BJ index identities. The Tushare BJ fallback in code is snapshot-only, not a current `minute_bar_1m` source.

Quality-visible blocker plus excluding-blocker scoped C1 is allowed for the next prompt only.

## BJ Index Blocker Proof

- `index:BJ:899050`: expected `240` rows through `15:00`; actual `0` rows from `MootdxTodayMinuteAdapter`; do not write minute facts.
- `index:BJ:899601`: expected `240` rows through `15:00`; actual `0` rows from `MootdxTodayMinuteAdapter`; do not write minute facts.

The blockers are visible in this artifact pair and the next scoped C1 execute must write two `common_market_data_quality_item` rows under:

`today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`

## Frozen Excluding-Blocker Scope

- excluded identities: `index:BJ:899050`, `index:BJ:899601`
- included stock identities: `1841`
- included index identities: `81`
- included board identities: `127`
- included total identities: `2049`
- expected full-day rows after scoped C1: stock `441840`, index `19440`, board `30480`, total `491760`

Current repaired coverage before scoped C1 is `172` rows per included identity with max `13:52`; the next C1 execute must prove `240` rows through `15:00` for every included identity before writing.

## Lineage Proof

- source_condition_run_id: `condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- source_subscription_run_id: `market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- subscription status: `passed`
- subscription source_condition_run_id matches repaired N2: `true`
- planned today minute target rows now: `0`
- planned full-day metric rows now: `0`

## Exclusion Proof

- old-v1 metric run is stale for repaired lineage and was not used as active proof.
- until_1352 metric is not full-day proof and was not used as full-day evidence.

## Forbidden Scope Proof

- no C1 backfill execute
- no B2 metric execute
- no N4/N5/N6
- no old-system read/write
- no outbox/inbox/checkpoint mutation
- no worker/scheduler
- no voice/mobile/sim/position/order/real trade

## Allowed Next Prompt

```text
layer_role=N3_market_data.

Enter N3_20260617_FULL_DAY_CURRENT_MINUTE_EXCLUDING_BJ_BLOCKER_SCOPED_C1_BACKFILL_EXECUTE.

Use:
- trade_date=20260617
- source_condition_run_id=condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- source_subscription_run_id=market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- policy_gate_artifact=docs/N3_20260617_FULL_DAY_CURRENT_MINUTE_MISSING_BJ_INDEX_POLICY_OR_ALTERNATE_SOURCE_GATE.json
- planned_today_minute_run_id=today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- excluded_quality_blocker_identities=index:BJ:899050,index:BJ:899601

Goal: execute bounded N3 C1 full-day current minute backfill only for the frozen excluding-blocker scope: stock 1841, index 81, board 127, total 2049 included identities. Before any DB write, prove every included identity has exactly 240 current minute_bar_1m rows through 15:00 from an N3-allowed source. Write zero minute facts for index:BJ:899050 and index:BJ:899601, and write quality-visible blocker rows for both excluded identities in common_market_data_quality_item or fail before DB write. Do not execute B2 metric and do not enter N4/N5/N6. Do not use old-v1 active proof or until_1352 metric as full-day proof. Do not consume/update outbox/inbox/checkpoint, do not start scheduler/worker, and do not touch voice/mobile/sim/position/order/real trade or old system.
```
