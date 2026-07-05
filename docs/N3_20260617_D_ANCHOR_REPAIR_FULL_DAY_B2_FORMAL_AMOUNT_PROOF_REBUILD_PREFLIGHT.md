# N3_20260617_D_ANCHOR_REPAIR_FULL_DAY_B2_FORMAL_AMOUNT_PROOF_REBUILD_PREFLIGHT

- result: `PREFLIGHT_BLOCKED`
- metric_run_id_under_repair: `action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- C1 15:00 coverage: stock `1841/1841`, index `81/81`, board `127/127`, all 240 rows
- existing formal proof rows: `0`; D/W/M/Q/Y non-null rows: `0` for stock/index/board
- D/W/M/Q/Y source readiness: stock `1819/1841`, index `81/81`, board `127/127`
- missing formal-period stock identities: `22`
- previous-day same-window calibration source: `missing` for D-anchor lineage
- canonical distribution: `{'BUY_HINT': 59, 'SELL': 2021, 'BUY': 1939, 'SELL_HINT': 165, 'SELL:FULL': 28, 'BUY:FULL': 110}`
- BJ blockers preserved: `2` identities, quality rows visible
- old-v1 / semantic_repair / until_1352 refs in current metric: `{'old_v1': {'stock': 0, 'index': 0, 'board': 0}, 'semantic_repair': {'stock': 0, 'index': 0, 'board': 0}, 'until_1352': {'stock': 0, 'index': 0, 'board': 0}}`
- no N4 handoff: `N4 handoff is blocked until an N3 formal amount proof rebuild post-review PASS supersedes this preflight.`

## Blockers

- `n3_formal_b2_existing_metric_lacks_formal_proof`: formal rows in trace_json=0, D/W/M/Q/Y non-null columns=0 across all assets
- `n3_formal_b2_n2_period_baseline_dwmqy_complete`: missing identities=22; stock identities_all_DWMQY_ready=1819/1841; index=81/81; board=127/127
- `n3_formal_b2_buy_sell_hint_30m_calibration_source_available`: no D-anchor previous-day preload run; previous-day rows stock/index/board=0/0/0

## Artifacts

- JSON: `docs/N3_20260617_D_ANCHOR_REPAIR_FULL_DAY_B2_FORMAL_AMOUNT_PROOF_REBUILD_PREFLIGHT.json`
- Existing metric rollback SQL: `/Users/chuanfuchen/Documents/A股监控系统v3/sql/N3_20260617_d_anchor_repair_full_day_action_confirmation_metric_rollback.sql`

## Allowed Next Prompt

```text
layer_role=N3_market_data.

Enter N3_20260617_D_ANCHOR_REPAIR_FULL_DAY_B2_FORMAL_AMOUNT_PROOF_BLOCKER_RESOLUTION_GATE.

Use:
- trade_date=20260617
- source_condition_run_id=condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- source_subscription_run_id=market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- source_today_minute_run_id=today_minute_bar_1m_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1
- blocked_preflight_artifact=docs/N3_20260617_D_ANCHOR_REPAIR_FULL_DAY_B2_FORMAL_AMOUNT_PROOF_REBUILD_PREFLIGHT.json

Goal: resolve N3 formal proof blockers before any B2 repair execute. Must decide whether to acquire D-anchor previous-day same-window minute source for 20260616, and whether the 22 stock Q/Y N2 baseline gaps require N2_condition repair or N3 quality-visible blocker policy. Do not execute B2, do not enter N4/N5/N6, do not consume/update outbox/inbox/checkpoint, do not start worker/scheduler, and do not touch old system or voice/mobile/sim/position/order/real trade.
```
