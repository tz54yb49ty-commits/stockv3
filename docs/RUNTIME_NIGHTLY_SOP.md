# Nightly Runtime SOP v0

更新日期：2026-08-21
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

## 6. Disk cleanup fail-closed override

`runtime_hot_cleanup_archive_gated_disk_governance_v1` 高于历史 nightly cleanup
说明。`direct-delete-no-archive` 不再是合法模式；不得手工补跑 01:00 cleanup。
任何实际操作必须由独立请求选择且只选择 quiesce、archive-verified local
reclaim、Time Machine snapshot fallback、archive-gated restore 一个阶段。定义
policy 的会话不得执行它。

archive 必须由独立 `N1_ingestion` gate 先完成逐文件 manifest、全量 SHA equality
和隔离 restore proof。runtime_control 不归档、不删数据库业务事实；local reclaim
只消费冻结的 exact allowlist。restore 后验收仅等待自然 01:00，连续 5 次自然
PASS 属于后续 Gate 3 验收，不得用手工运行代替。

持久修复采用独立 exact N1 archive-only daily label
`com.ashare-v3.n1.local-artifact-archive-daily`：自然 23:00 为次日 cleanup date
生成 verified batch，并只在全部证据 PASS 后原子发布
`/Volumes/MacRaid/stock_db_archive/v3_runtime_artifacts/current_verified_batch.json`。
安装该 label 只能由独立 runtime_control 请求满足
`n1_local_artifact_archive_daily_bounded_install_v1` 后执行；定义 policy 的会话不得
安装或运行。自然 01:00 cleanup 只接受当前日期 pointer 并以 `--local-only` 运行，
不得计划或执行数据库 DELETE。23:00 未完成、失败或 pointer 过期时，01:00 必须
fail-closed，不等待、不 retry、不手工补跑。
