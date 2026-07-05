# N1 Trade Calendar 20260527 Patch Contract

日期：2026-05-27
layer_role：`N1_ingestion`
状态：`DESIGN_PASS`

## Purpose

补齐 `common_trade_calendar` 中 `20260527` 的交易日明细，并激活 `SSE:20260527` 的 `trade_calendar` source version，以解除 20260527 N3 subscription 的 calendar blocker。

本合同不授权 execute。默认 runner 只做 preflight：只读 PostgreSQL、查询 Tushare `trade_cal`、写 preflight artifact，不写数据库。

## Identity

```text
source_batch_id = trade_calendar_20260527_patch_v1
source_version  = trade_calendar_20260527_patch_v1
scope_key       = SSE:20260527
```

## Source Policy

优先使用：

```text
Tushare trade_cal
exchange = SSE
trade_date = 20260527
```

fallback 只有在显式传入 `--allow-minimal-fallback` 时允许：

```text
依据 common_trade_calendar 中 20260526.next_trade_date=20260527
source = manual.calendar_patch
quality gate 写 P2 warning: manual_calendar_patch_used
```

## Future Write Scope

未来 execute 只允许单事务写：

```text
common_ingest_batch
common_trade_calendar
common_active_source_version
common_quality_gate_result
```

禁止：

```text
stock_daily_bar_fact
index_daily_bar_fact
board_daily_bar_fact
stock_daily_basic
stock_financial_metrics_fact
condition source
Parquet
common_event_outbox
common_event_inbox
checkpoint
N2/N3/N4/N5/N6
worker
old system
real trading
```

## Execute Flags

未来 execute 必须同时具备：

```text
--execute
--user-confirmed
--postgres-commit-enabled
```

建议命令：

```bash
PYTHONPATH=src python3 scripts/run_trade_calendar_patch_20260527_once.py \
  --trade-date 20260527 \
  --execute \
  --user-confirmed \
  --postgres-commit-enabled
```

## Quality Gate

P0 gate：

```text
target_calendar_missing_before_patch
active_trade_calendar_missing_before_patch
patch_batch_absent
patch_active_conflict_absent
patch_quality_conflict_absent
previous_calendar_next_trade_date
tushare_trade_cal_available
calendar_target_open
calendar_prev_trade_date
calendar_next_trade_date_present
calendar_patch_scope_limited
```

fallback gate：

```text
manual_calendar_patch_used = P2 warning
```

## Rollback

Rollback SQL：

```text
sql/N1_trade_calendar_20260527_patch_rollback.sql
```

Rollback 只允许按 `source_batch_id/source_version/trade_date=20260527/scope_key=SSE:20260527` 清理本次 calendar patch，并删除或恢复 `SSE:20260527` 的 active source version。不碰 daily fact、condition source、Parquet、outbox、N2/N3/N4/N5/N6。
