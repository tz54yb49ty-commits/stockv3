# Premarket N1 -> N2 -> N3 -> A1 Pipeline Runbook

更新日期：2026-06-02

范围：`runtime_control` 只读 runbook / checker。本文档不授权 execute、数据库写入、rollback、outbox consumption、worker、B1/N4/N5/N6、push/voice/mobile/sim/position/real trade。

## 1. Readiness 检查

进入流水线前先运行只读 checker：

```bash
PYTHONPATH=src python3 scripts/plan_premarket_pipeline_readiness.py \
  --source-trade-date <SOURCE_TRADE_DATE> \
  --for-trade-date <FOR_TRADE_DATE> \
  --condition-run-id <CONDITION_RUN_ID> \
  --json
```

checker 只读：

```text
docs/*.json
sql/*.sql
```

checker 不连接数据库、不执行 N1-N6、不执行 rollback、不消费 outbox、不启动 worker。

readiness 必须确认：

```text
run_id rules = PASS
rollback registry = PASS
N1/N2/N3/A1 stage status in READY/PASS
missing rollback paths = []
cross_layer_risk = not_detected_static
worker_risk = manual_pre_execute_check_required
```

执行前仍需人工确认当前机器没有影响本 gate 的 worker/consumer。

## 2. N1 输入 / 输出

输入：

```text
source_trade_date = T
Tushare / TDX / 本地 TDX txt
stock/index/board daily
stock_daily_basic
stock_financial
index_membership
board_membership
common_trade_calendar
```

输出：

```text
official_daily_ingest_T_v1
condition_source_activation_T_v1
stock_daily_T_v1 / index_daily_T_v1 / board_daily_T_v1
stock_daily_basic_T_v1 / stock_financial_T_vN
index_membership_T_v1 / board_membership_T_v1
common_active_source_version
quality gates
rollback SQL
```

N1 禁止进入 N2/N3/N4/N5/N6，禁止拉盘中分钟 K。

## 3. N2 输入 / 输出

输入：

```text
N1 active source_version for source_trade_date=T
for_trade_date = next open date after T
prev_trade_date = T
```

输出：

```text
condition_layer_T_source_T_vN
common_condition_run.status = passed_active
stock/index/board_condition_basis
stock/index/board_condition_pool
stock/index/board_minute_target_scope
stock/index/board_condition_display_basis
common_condition_quality_item
rollback SQL
```

N2 只生成条件语义和行情范围，不拉行情、不写 N3/N4/N5/N6。

## 4. N3 Subscription 输入 / 输出

输入：

```text
condition_run_id = condition_layer_T_source_T_vN
stock/index/board_minute_target_scope
for_trade_date
```

输出：

```text
market_data_subscription_<FOR_TRADE_DATE>_<CONDITION_RUN_ID>
common_market_data_run
common_market_data_quality_item
common_market_data_subscription_candidate
common_market_data_subscription
common_market_data_pull_plan
rollback SQL
```

N3 subscription 只写 control rows，不拉行情、不写 snapshot/minute facts、不写 outbox。

## 5. A1 输入 / 输出

输入：

```text
subscription_run_id
common_market_data_subscription where required_data_kind=previous_day_minute_bar_1m
previous_day_minute_date = T
```

输出：

```text
previous_day_minute_preload_T_for_<FOR_TRADE_DATE>__<SUBSCRIPTION_RUN_ID>
stock/index/board_minute_bar_1m
stock/index/board_previous_day_minute_preload_status
common_market_data_run
common_market_data_quality_item
rollback SQL
```

A1 不写 outbox/inbox/checkpoint，不进入 B1/N4/N5/N6。

## 6. Run ID 规则

```text
N1 official daily batch:
official_daily_ingest_<SOURCE_TRADE_DATE>_v1

N1 condition source batch:
condition_source_activation_<SOURCE_TRADE_DATE>_v1

N2 condition run:
condition_layer_<SOURCE_TRADE_DATE>_source_<SOURCE_TRADE_DATE>_vN

N3 subscription:
market_data_subscription_<FOR_TRADE_DATE>_<CONDITION_RUN_ID>

A1 previous-day preload:
previous_day_minute_preload_<SOURCE_TRADE_DATE>_for_<FOR_TRADE_DATE>__<SUBSCRIPTION_RUN_ID>
```

如果目标 run_id 已存在且需要重跑，不覆盖旧 run；必须另走 rebuild gate，使用：

```text
<base_run_id>_rebuild_<YYYYMMDD>_vN
```

## 7. Rollback 规则

rollback registry 至少包含：

```text
sql/N1_official_daily_<SOURCE_TRADE_DATE>_ingestion_rollback.sql
sql/N1_condition_source_<SOURCE_TRADE_DATE>_activation_rollback.sql
sql/N2_condition_layer_<SOURCE_TRADE_DATE>_rollback.sql
sql/N3_subscription_<FOR_TRADE_DATE>_rollback.sql
sql/N3_A1_previous_day_minute_<FOR_TRADE_DATE>_rollback.sql
```

若 N2 run 是当前 v6 level-score lineage，N2 rollback path 为：

```text
sql/N2_level_score_<SOURCE_TRADE_DATE>_v6_rollback.sql
```

rollback 执行必须另走对应 layer gate。runtime_control 只登记路径，不执行 SQL。

## 8. Nightly SOP

```text
1. runtime_control: run read-only checker.
2. N1_ingestion: official daily + condition source dry-run/preflight.
3. N1_ingestion: execute only after explicit user confirmation.
4. runtime_control: register N1 result.
5. N2_condition: dry-run/preflight.
6. N2_condition: execute only after explicit user confirmation.
7. runtime_control: register N2 result.
8. N3_market_data: subscription dry-run/preflight.
9. N3_market_data: execute subscription only after explicit user confirmation.
10. runtime_control: register N3 subscription result.
11. N3_market_data: A1 dry-run/preflight.
12. N3_market_data: execute A1 only after explicit user confirmation.
13. runtime_control: register A1 result and stop.
```

B1/N4/N5/N6、delivery、notification、worker、push/voice/mobile/sim/position/real trade 必须另开 gate。

## 9. Fail-Fast 条件

立即 BLOCKED：

```text
P0 > 0
trade calendar missing or inconsistent
active source_version not unique
active condition run not unique
run_id rule mismatch
target run_id conflict without rebuild gate
missing rollback SQL path
outbox/inbox/checkpoint refs found in execute preflight
downstream refs found before rollback/overwrite
worker/consumer risk cannot be scoped
any stage attempts to enter B1/N4/N5/N6
old system touched
```

## 10. 一页 Runbook

```text
Input:
  SOURCE_TRADE_DATE=T
  FOR_TRADE_DATE=next_open_date(T)
  CONDITION_RUN_ID=condition_layer_T_source_T_vN

Check:
  PYTHONPATH=src python3 scripts/plan_premarket_pipeline_readiness.py \
    --source-trade-date T \
    --for-trade-date FOR_TRADE_DATE \
    --condition-run-id CONDITION_RUN_ID \
    --json

Expected:
  result=PASS
  rollback_registry=PASS
  run_id_rules=PASS
  N1/N2/N3/A1 status READY or PASS

Execute sequence:
  N1_ingestion only after explicit confirmation
  N2_condition only after explicit confirmation
  N3_market_data subscription only after explicit confirmation
  N3_market_data A1 only after explicit confirmation

Stop:
  Do not enter B1/N4/N5/N6.
  Do not consume outbox.
  Do not start worker.
  Do not push/voice/mobile/sim/position/real trade.
```
