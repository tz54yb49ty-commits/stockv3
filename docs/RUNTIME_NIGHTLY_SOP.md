# Nightly Runtime SOP v0

更新日期：2026-05-27
范围：nightly runtime 控制面 SOP，不授权 execute、数据库写入、worker 或真实交易。

## 1. 入口

进入本 SOP 必须先确认：

```text
layer_role=runtime_control
本会话只做 runtime orchestration / dashboard
不修改 N1-N6 execute contract
不执行 nightly run
```

## 2. Dashboard

生成只读 dashboard：

```bash
PYTHONPATH=src python3 scripts/plan_runtime_pipeline_dashboard.py --trade-date <YYYYMMDD>
```

生成 JSON：

```bash
PYTHONPATH=src python3 scripts/plan_runtime_pipeline_dashboard.py --trade-date <YYYYMMDD> --json
```

启动只读 Web dashboard：

```bash
PYTHONPATH=src python3 scripts/run_runtime_dashboard_web.py
```

路由：

```text
GET /runtime/
GET /runtime/{trade_date}
GET /api/runtime/{trade_date}/dashboard
```

检查项：

```text
pipeline_name = nightly_runtime_v0
layer_role = runtime_control
所有 stage 初始为 WAIT_MANUAL_CONFIRM
command registry 只登记命令
rollback registry 只登记 rollback SQL path
side_effects 全部为 false
```

## 3. Manual Gate

每个 stage 必须停在：

```text
WAIT_MANUAL_CONFIRM
```

进入具体 execute 前必须切换到对应 layer_role：

```text
calendar / n1_official_daily / n1_condition_source -> N1_ingestion
n2_condition_layer -> N2_condition
n3_subscription / a1_previous_day_preload / b1_realtime_snapshot_fact_only -> N3_market_data
```

`runtime_control` 不代替这些层执行命令。

## 4. 回滚登记

dashboard 只显示 rollback SQL 路径。执行 rollback 必须另开对应 layer_role 会话，并重新确认：

```text
目标 run_id
影响表
delivered/delivering / inbox / checkpoint refs
rollback SQL
用户明确授权
```

## 5. 禁止事项

```text
不得用 runtime_control 执行 N1-N6 command
不得在 runtime_control 中执行 rollback
不得启动长期 worker 或 bounded worker smoke
不得消费 N3/N4/N5 outbox
不得写 N6 projection / voice / mobile / sim / real trade
不得触碰旧系统
```
