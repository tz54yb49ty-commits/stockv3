# N4 Projection Matcher 20260608 Until 15:00 Unified Output Retry Post Review

## Result

POST_REVIEW_PASS

## Target

- target_run_id: `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- rollback SQL: `sql/N4_projection_matcher_20260608_until_1500_unified_output_retry_rollback.sql`

## Execute Proof Summary

- execute report result: `EXECUTED`
- common_trigger_run.status: `passed`
- P0/P1/P2: `[0, 0, 0]`
- worker_started: `False`
- downstream_layers_touched: `False`

## Row Count Proof

| Table | Actual |
|---|---:|
| common_trigger_run | 1 |
| common_trigger_quality_item | 10 |
| common_trigger_state | 556 |
| common_trigger_match | 556 |
| common_event_outbox | 556 |
| common_event_inbox | 2155 |
| common_event_consumer_checkpoint | 2155 |

Expected row counts match: `True`

## Event / State Proof

- TriggerMatched: `556`
- TriggerPendingMarketData: `0`
- TriggerStateChanged: `0`
- N4 outbox status: `{'pending': 556}`

## Unified Output Proof

- required unified fields missing: `0`
- condition_signal_type present: `556/556`
- requested_periods present: `556/556`
- triggered_period_details present: `556/556`
- projection_30m_* fields present: `556/556`
- invalid signal_type: `0`
- runtime_signal mismatch: `0`
- action_mark emitted: `0`
- trigger_price null: `0`
- n5_entry_allowed invalid: `0`
- formal period contains 30m: `0`
- HINT formal pollution: `0`

## HINT Event Time Proof

- BUY_HINT event_time: `116/116`
- SELL_HINT event_time: `6/6`
- HINT trigger_period=30m: `122/122`
- HINT primary_trigger_period=null: `122/122`
- HINT triggered_periods=[]: `122/122`
- HINT all_trigger_periods=[]: `122/122`

## Six-Family Semantic Proof

- BUY: `299`
- SELL: `135`
- BUY:FULL: `0`
- SELL:FULL: `0`
- BUY_HINT: `116`
- SELL_HINT: `6`
- B_BUY/S_SELL: `415/141`
- trigger_mark_candidate: `{'30m_shrink': 6, '30m_volume': 116, 'normal': 434}`
- FULL context rows: `86`
- FULL TriggerMatched: `0`
- FULL interpretation: FULL context exists, but no BUY:FULL/SELL:FULL TriggerMatched rows were produced because this run had no D transition trigger for FULL.

## Upstream Preservation Proof

- N3 MarketSnapshotUpdated source run: `realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- pending/delivered/delivering: `2155/0/0`
- N3 snapshot facts stock/index/board: `1945/83/127`
- N3 projection facts stock/index/board: `1945/83/127`
- old FULL repair retry lineage common_trigger_run/common_event_outbox: `1/556`

## Downstream Clean Proof

- N5 refs total: `0`
- N6/user/delivery/sim/position refs total: `0`
- event ledger refs: `0`
- delivery attempt refs: `0`

## Rollback Proof

- rollback SQL regeneration report: `REGENERATION_PASS`
- hard-fail before first DELETE/UPDATE: `True`
- guards delivered/delivering: `True`
- guards N5 refs: `True`
- guards N6/user/sim/order/trade/position refs: `True`
- guards event ledger/delivery attempts if tables exist: `True`
- excludes scoped N4 consumer checkpoint false positive: `True`
- deletes only scoped N4 unified output retry rows: `True`
- no DROP/TRUNCATE/CASCADE: `True`
- rollback executed: `false`

## Forbidden Scope Proof

- SQL executed: `false`
- DB write performed: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- N5/N6 entered: `false`
- worker started: `false`
- delivery/push/voice/mobile: `false`
- sim/position/pnl/real_trade: `false`
- proposal/order/trade: `false`
- old system touched: `false`

## Validation

- JSON parse: `PASS`
- live DB row count proof: `PASS`
- unified output semantic scan: `PASS`
- HINT event_time proof: `PASS`
- upstream preservation proof: `PASS`
- downstream refs scan: `PASS`
- rollback static check: `PASS`
- git diff --check: `PASS`

## Next Gate

Allow entering `N5_ACTION_CONFIRMATION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_READINESS_GATE`.
