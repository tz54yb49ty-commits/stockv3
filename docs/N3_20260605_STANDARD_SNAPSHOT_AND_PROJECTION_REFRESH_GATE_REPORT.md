# N3 20260605 Standard Snapshot And Projection Refresh Gate

Status: REFRESH_PLAN_PASS

```text
for_trade_date=20260605
source_condition_run_id=condition_layer_20260604_source_20260604_v1
current_snapshot_run_id=realtime_snapshot_20260605_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1
current_today_minute_run_id=today_minute_bar_1m_20260605_until_0933__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1
P0/P1/P2=0/2/0
execute_final_gate_allowed=false
```

## B1 Snapshot Blocker

Current B1 rows are complete, but stock and index are not live-quality passed:

```text
stock rows=1952 quality_status=partial source_time_status=source_time_missing_or_preopen
index rows=9 quality_status=partial source_time_status=source_time_missing_or_preopen
board rows=428 quality_status=passed source_time_status=source_time_confirmed
missing_source_rows=0
BJ stock/index rows in current B1 scope=0/0
```

N4 ordinary snapshot plans therefore remain pending with `snapshot_quality_not_passed`.

Required refresh: generate a new live B1 fact-only refresh run, proposed:

```text
realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1
```

## Projection Blocker

No 20260605 projection facts exist for the current lineage:

```text
stock/index/board_realtime_projection_metric=0/0/0
stock/index/board_projection_enrichment_v4_metric=0/0/0
stock/index/board_action_confirmation_projection_metric=0/0/0
```

N4 projection-trigger candidates therefore remain pending with `projection_fact_not_available_in_local_snapshot_dry_run`.

Required refresh sequence:

```text
1. B1 live2 snapshot contract/preflight/rollback
2. C1 current-minute dry-run/execute for latest closed minute
3. B2 realtime projection dry-run/contract/preflight/rollback
4. Projection enrichment v4 refresh after B2
5. Action-confirmation metric only after N4 TriggerMatched exists
```

## Future Write Scope

Allowed only for future separately confirmed execute gates:

```text
B1: common_market_data_run, common_market_data_quality_item, stock/index/board_realtime_daily_snapshot
C1: common_market_data_run, common_market_data_quality_item, stock/index/board_minute_bar_1m
B2: common_market_data_run, common_market_data_quality_item, stock/index/board_realtime_projection_metric
projection_enrichment_v4: common_market_data_run, common_market_data_quality_item, stock/index/board_projection_enrichment_v4_metric
```

Forbidden:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
N4/N5/N6 tables
worker
delivery / push / voice / mobile / sim / position / real_trade
old_system
```

## Next Prompt

```text
layer_role=N3_market_data。
请进入 20260605 N3 B1 live2 snapshot + C1 current-minute + B2 realtime projection refresh dry-run/contract/preflight gate。
只允许生成/刷新 N3 artifacts 和只读 source readiness，不执行；若 PASS 再进入 execute final gate。
```
