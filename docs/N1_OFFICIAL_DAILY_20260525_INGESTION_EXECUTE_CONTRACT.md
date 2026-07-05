# N1 Official Daily 20260525 Ingestion Execute Contract

日期：2026-05-26
layer_role：`N1_ingestion`
状态：`DESIGN_PASS`

## 1. Purpose

本 execute contract 用于未来明确授权后补齐 `20260525` official daily fact，使 N3-EOD snapshot refresh 可以重新 preflight。

本文件不是 execute 授权。本轮已实现 source fetch adapter routing、transform validation 与 PostgreSQL commit transaction 逻辑，但默认路径仍不执行入库、不拉行情、不写数据库、不写 Parquet。

本轮 runner wiring 状态：

```text
CLI execute_path_wired = true
all four flags present -> source fetch -> validation -> preconditions -> commit plan -> execute_commit_transaction
missing any execute/final-gate flag -> BLOCKED before source fetch / commit
tests use mock source fetch only
```

## 2. Identity

```text
contract_batch_id = official_daily_ingest_20260525_v1
contract_source_version = official_daily_ingest_20260525_v1

stock source_version = stock_daily_20260525_v1
index source_version = index_daily_20260525_v1
board source_version = board_daily_20260525_v1
```

`common_ingest_batch` 建议写入一条 umbrella batch：

```text
batch_id = official_daily_ingest_20260525_v1
trade_date = 20260525
data_domain = common
data_type = official_daily_fact_ingestion
source = n1.official_daily.composite
source_version = official_daily_ingest_20260525_v1
row_count = stock_rows + index_rows + board_rows
rollback_strategy = delete_by_source_batch_id_then_restore_previous_active_source_version
```

三张 fact 表使用：

```text
source_batch_id = official_daily_ingest_20260525_v1
source_version = stock_daily_20260525_v1 / index_daily_20260525_v1 / board_daily_20260525_v1
```

## 3. Execute Flags

未来 runner 必须要求双确认：

```text
--execute
--user-confirmed
```

进入最终 execute gate 时，还必须显式打开：

```text
--source-fetch-enabled
--postgres-commit-enabled
```

缺少任一参数时，runner 只能输出 dry-run/preflight 报告，必须退出且不写库。

建议命令形态：

```bash
PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260525_once.py \
  --trade-date 20260525 \
  --execute \
  --user-confirmed \
  --source-fetch-enabled \
  --postgres-commit-enabled
```

当前 preflight run 不会使用上述 final gate 标志执行真实拉取或提交；最终执行仍需另开总控确认。

## 4. Idempotency And Existing Version Policy

默认策略：阻断，不 overwrite。

未来 execute 前必须检查：

```text
common_ingest_batch.batch_id = official_daily_ingest_20260525_v1 不存在
stock_daily_bar_fact source_version = stock_daily_20260525_v1 不存在
index_daily_bar_fact source_version = index_daily_20260525_v1 不存在
board_daily_bar_fact source_version = board_daily_20260525_v1 不存在
common_active_source_version scope 20260525 for stock_daily/index_daily/board_daily 不存在
```

如果已存在：

```text
BLOCKED_existing_source_version_or_active_scope
不得 ON CONFLICT DO NOTHING 静默成功
不得覆盖 active_source_version
必须先走 rollback 或另开 v2 source_version gate
```

## 5. Transaction Boundary

execute 必须先完成外部 source fetch 和 dry-run quality 计算。只有 P0=0 时才能进入 PostgreSQL transaction。

当前实现状态：

```text
source_fetch_adapter_routing = implemented
source_fetch_actual_external_call = disabled by default
source_transform_validation = implemented
postgres_single_transaction_commit = implemented
cli_execute_pipeline_wiring = implemented
parquet_write = false
execute_authorized = false
final_gate_required = true
```

单事务写入顺序：

```text
1. common_ingest_batch umbrella row
2. stock_daily_bar_fact rows
3. index_daily_bar_fact rows
4. board_daily_bar_fact rows
5. common_quality_gate_result rows
6. common_active_source_version rows for:
   stock / stock_daily / 20260525
   index / index_daily / 20260525
   board / board_daily / 20260525
7. common_ingest_batch status=passed, finished_at=now()
```

事务提交条件：

```text
P0 = 0
stock EOD coverage = 2052/2052
index EOD coverage = 9/9
board EOD coverage = 127/127
fixed 9 index coverage = 9/9
duplicate identity_key = 0
same-code contamination = 0
forbidden source usage = 0
forbidden write scope = 0
```

如果 execute 过程中出现 P0：

```text
ROLLBACK transaction
不保留 partial fact
不更新 active_source_version
不写 N3/N4/N5/N6
```

## 6. Parquet Policy

初版 execute contract：PostgreSQL only，不写 Parquet。

理由：

```text
当前目标是解除 N3-EOD missing_official_daily_fact blocker。
Parquet 归档会扩大权限和 rollback 面。
本次 source_batch_id/source_version、quality gate、active source_version 已足够支撑 EOD preflight 重新读取 official daily fact。
```

如未来需要归档，必须另开 N1 Parquet manifest gate，并新增 manifest rollback。

## 7. Future Allowed Write Scope

仅允许写：

```text
common_ingest_batch
common_quality_gate_result
common_active_source_version
stock_daily_bar_fact
index_daily_bar_fact
board_daily_bar_fact
```

## 8. Future Forbidden Scope

禁止写：

```text
stock_daily_basic
stock_financial_metrics_fact
stock/index/board realtime/minute/closed/projection/eod tables
common_market_data_run
common_market_data_quality_item
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
condition tables
trigger/action/user/voice/mobile/sim/position tables
Parquet / manifest in initial execute contract
old system
worker
real trading
```

禁止读取作为 official daily 来源：

```text
N3 realtime snapshot
C2 closed summary
C2B enrichment
C3 MinuteBarClosed outbox
旧系统 monitor.db
手工数据
```

## 9. EOD Handoff

入库 passed 后，N3-EOD 只能通过以下方式读取 official daily fact：

```sql
SELECT data_domain, data_type, scope_key, source_version
FROM common_active_source_version
WHERE scope_key = '20260525'
  AND (
    (data_domain = 'stock' AND data_type = 'stock_daily')
    OR (data_domain = 'index' AND data_type = 'index_daily')
    OR (data_domain = 'board' AND data_type = 'board_daily')
  );
```

然后按 `trade_date + source_version + identity_key` 读取三张物理分表。

示例：

```sql
SELECT *
FROM stock_daily_bar_fact
WHERE trade_date = '20260525'
  AND source_version = 'stock_daily_20260525_v1'
  AND official_daily_proof IS TRUE;
```

EOD 禁止：

```text
直接 SELECT MAX(trade_date)
扫描所有 source_version 猜最新
使用 N3 runtime fact 替代 official daily
使用 C2/C2B/C3 派生事实替代 official daily
```

## 10. Post Execute Validation

未来 execute 后必须只读验证：

```text
stock_daily_bar_fact source_version stock_daily_20260525_v1 row_count > 0
index_daily_bar_fact source_version index_daily_20260525_v1 row_count > 0
board_daily_bar_fact source_version board_daily_20260525_v1 row_count > 0
EOD expected stock coverage = 2052
EOD expected index coverage = 9
EOD expected board coverage = 127
active_source_version 3 rows written
quality P0 = 0
common_event_outbox unchanged
N2/N3/N4/N5/N6 row summary unchanged except later separately authorized EOD preflight
```

## 11. Runner / Preflight Implementation

本合同已补充 runner / preflight 实现，但仍不是 execute 授权。

实现路径：

```text
src/ashare_v3/ingestion/official_daily_ingestion_execute.py
scripts/run_official_daily_ingestion_20260525_once.py
tests/test_official_daily_ingestion_execute.py
```

preflight artifact：

```text
docs/N1_OFFICIAL_DAILY_20260525_INGESTION_EXECUTE_PREFLIGHT.md
docs/N1_official_daily_20260525_ingestion_execute_preflight.json
```

runner 当前只做：

```text
read-only baseline guard
dry-run report integration
write scope guard
rollback SQL integration
dual-confirmation validation
```

runner 当前明确不做：

```text
不拉 Tushare / TDX / Mootdx
不写 PostgreSQL
不写 Parquet
不改 active_source_version
不写 common_event_outbox / inbox / checkpoint
不进入 N3/N4/N5/N6
不启动 worker
不触碰旧系统
不真实交易
```

当前 preflight 结论：

```text
result = PREFLIGHT_PASS
runner_readiness = ready_for_final_gate
execute_authorized = false
missing_official_daily = stock 2052 / index 9 / board 127 / total 2188
current_official_daily_rows = 0 / 0 / 0
EOD snapshot rows = 0 / 0 / 0
C3 MinuteBarClosed outbox pending = 17432
```

下一步只能进入单独的 final gate；final gate 必须重新确认 source fetch 与 commit 权限，不能把本 preflight 当作 execute。
