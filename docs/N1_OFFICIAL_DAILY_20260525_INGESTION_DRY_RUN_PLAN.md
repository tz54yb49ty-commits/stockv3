# N1 Official Daily 20260525 Ingestion Dry-Run Plan

日期：2026-05-26
layer_role：`N1_ingestion`
状态：`DESIGN_PASS`

## 1. 目标

为 `20260525` 设计 N1 official daily fact 入库 dry-run，用于解除 N3-EOD 的 `missing_official_daily_fact` blocker。

本 dry-run 只生成计划和验收报告，不拉行情、不连接数据库、不执行 SQL、不写 PostgreSQL、不写 Parquet、不修改 active source version。

## 2. 上游证据

N3-EOD dry-run / preflight 当前结论：

```text
eod_run_id = eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
blocker = missing_official_daily_fact
official_daily_missing = 2188
expected EOD coverage:
  stock = 2052
  index = 9
  board = 127
  total = 2188
```

当前 N1 `20260525` official daily fact before execute：

```text
stock_daily_bar_fact = 0
index_daily_bar_fact = 0
board_daily_bar_fact = 0
active stock_daily/index_daily/board_daily source_version for scope 20260525 = none
```

## 3. Batch And Version

本 gate 使用一个 umbrella batch 组织三类 official daily fact，三张 fact 表仍保留各自独立 `source_version`。

```text
contract_batch_id = official_daily_ingest_20260525_v1
contract_source_version = official_daily_ingest_20260525_v1

stock source_version = stock_daily_20260525_v1
index source_version = index_daily_20260525_v1
board source_version = board_daily_20260525_v1
```

说明：

```text
source_batch_id 统一使用 official_daily_ingest_20260525_v1，便于本次 EOD blocker 修复按单一 batch 回滚。
source_version 仍按 stock/index/board 物理分表独立，便于 EOD 和后续层按 data_domain/data_type 精确读取。
```

## 4. Data Source Contract

允许来源：

| asset | target table | source contract |
|---|---|---|
| stock | `stock_daily_bar_fact` | Tushare official daily + `adj_factor` proof；`official_daily_proof=true` 后才允许激活。 |
| index | `index_daily_bar_fact` | TDX/Mootdx 指数日 K 优先；Tushare `index_daily` 兜底；固定 9 指数必须覆盖。 |
| board | `board_daily_bar_fact` | TDX/Mootdx 行业/板块日 K；board code 必须为 `881xxx`。 |

禁止来源：

```text
N3 realtime_daily_snapshot
N3 closed_30m_summary
N3 closed_30m_signal_enrichment
C3 outbox / MinuteBarClosed event
旧系统 daily_kline / monitor.db
手工造数
```

## 5. Dry-Run Required Output

dry-run runner 必须输出：

```text
expected_eod_coverage_objects:
  stock=2052
  index=9
  board=127
  total=2188

available_official_daily_before_execute:
  stock=0
  index=0
  board=0
  total=0

source_fetch_plan:
  stock: Tushare daily + adj_factor
  index: Mootdx index daily + Tushare index_daily fallback
  board: Mootdx board daily

expected_fetched_rows:
  report exact fetched/source-normalized rows after source probe
  also report EOD expected coverage subset rows

missing_objects:
  by asset_kind + identity_key

duplicate_identity_key:
  by target table and source_version

same_code_contamination:
  stock/index/board cross-namespace same code pollution = 0

fixed_9_index_coverage:
  9/9 required

board_881_coverage:
  all committed board rows must have board_code like 881xxx

stock_coverage_against_current_eod_expected_objects:
  2052/2052 required

P0/P1/P2:
  P0 must be 0 before execute contract can proceed
```

## 6. Canonical Daily Scope

本 contract 的 EOD blocker 是 `2188` 个 expected objects，但 N1 official daily fact 应保持 canonical daily 语义：

```text
stock_daily_bar_fact：可写入当日 Tushare official daily 返回的全量 A 股 daily rows。
index_daily_bar_fact：可写入 TDX 指数成分涉及指数 + 固定 9 指数。
board_daily_bar_fact：可写入本地 board identity 中 881xxx 行业/板块日 K。
```

EOD gate 只要求上述 canonical rows 覆盖当前 subscription expected objects：

```text
stock 2052/2052
index 9/9
board 127/127
```

不得为了通过 EOD 而只写 N3 snapshot 派生的非 official daily 数据。

## 7. Quality Gates

P0 gates：

```text
official_daily_source_versions_absent_before_execute
official_daily_active_scope_absent_or_explicitly_blocked
stock_official_daily_proof_coverage = 100%
stock_identity_key_coverage_for_committed_rows = 100%
index_identity_key_coverage_for_committed_rows = 100%
board_identity_key_coverage_for_committed_rows = 100%
eod_expected_stock_coverage = 2052/2052
eod_expected_index_coverage = 9/9
eod_expected_board_coverage = 127/127
fixed_9_index_coverage = 9/9
duplicate_identity_key = 0
same_code_contamination = 0
stock_88xxxx_violation = 0
board_881_code_shape = 100%
forbidden_source_usage = 0
forbidden_write_scope = 0
```

P1 gates：

```text
source_expected_full_day_row_count_variance
fallback_source_used_count
source_latency_or_retry_warning
```

P2 gates：

```text
non_eod_extra_rows_written_for_canonical_daily_scope
source_payload_field_optional_missing
```

## 8. Existing Runner Readiness

`scripts/run_real_daily_incremental.py` contains reusable N1 loader logic:

```text
load_stock_daily_day
load_index_daily_day
load_board_daily_day
run_persisted_batch
quality gate helpers
source normalization helpers
```

It is not safe to use directly for this gate execute without a wrapper because:

```text
it uses per-domain source_batch_id by default;
it can write Parquet archives;
it does not implement the umbrella batch_id official_daily_ingest_20260525_v1;
it does not enforce --execute + --user-confirmed for this EOD blocker contract;
it does not explicitly block existing 20260525 active source_version overwrite for this contract.
```

Recommended next runner:

```text
scripts/plan_official_daily_ingestion.py
scripts/run_official_daily_ingestion.py
```

Both must default to dry-run/no-write unless `--execute --user-confirmed` are both present.

## 9. Boundary

Future execute may only write:

```text
common_ingest_batch
common_quality_gate_result
common_active_source_version
stock_daily_bar_fact
index_daily_bar_fact
board_daily_bar_fact
```

This design explicitly does not authorize:

```text
PostgreSQL writes in this turn
Parquet writes in the first execute contract
N3 EOD snapshot writes
C3 outbox consumption
N2/N3/N4/N5/N6 writes
worker start
old system access
real trading
```
