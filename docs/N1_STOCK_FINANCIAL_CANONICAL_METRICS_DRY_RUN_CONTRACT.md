# N1 Stock Financial Canonical Metrics Dry-Run Contract

日期：2026-06-01
layer_role：N1_ingestion
状态：DESIGN_PASS draft

## 目的

本合同定义 `stock_financial_20260529_v2` 的 dry-run 输出和未来 execute 边界。N1 负责定稿 canonical financial metrics；N2 后续只读 active `stock_financial` source_version，不得重算。

## 输入

- active stock financial：`stock_financial_20260529_v1`
- target source_version：`stock_financial_20260529_v2`
- target batch：`stock_financial_canonical_20260529_v1`
- metric version：`financial_metric_v1`

## 来源优先级

TDX/Mootdx 财务包优先。Tushare 用于 daily_basic 市值、业绩预告、TDX 缺失股票的利润表/现金流兜底和 as-of announcement_date 补充。

## Dry-Run 输出

dry-run 必须输出：

- `expected_rows`
- `tdx_primary_count`
- `tushare_fallback_count`
- `asof_excluded_future_rows`
- `missing_announcement_date_excluded_rows`
- `interest_expense_missing_fallback_count`
- `ttm_annualized_count`
- `forecast_coverage_count`
- `score_distribution`
- `warning_distribution`
- `P0/P1/P2`
- baseline rows / batch conflict / active conflict
- `writes_performed=false`

## Quality 策略

P0：

- future announcement row 未排除。
- 缺 announcement date 且无法证明 as-of 安全的数据进入 canonical metrics。
- row count 与 expected 不一致。
- duplicate identity_key。
- active/batch/source_version 冲突。
- JSON payload 不可序列化。

P1：

- 利息费用缺失，使用财务费用替代。
- TDX 缺口由 Tushare 兜底。
- TTM 不足 4 季年化。
- forecast 缺失或口径弱。

P2：

- 非阻断性字段 coverage 分布和样本。

## 未来 Execute 写入范围

未来 execute 只能写：

```text
common_ingest_batch
common_quality_gate_result
common_active_source_version
stock_financial_metrics_fact
```

禁止写：

```text
condition_*
stock/index/board daily fact
outbox/inbox/checkpoint
Parquet
N2/N3/N4/N5/N6
worker
old system
real trading
```

## Rollback

未来业务写入 rollback 必须按：

```text
source_batch_id = stock_financial_canonical_20260529_v1
source_version = stock_financial_20260529_v2
source_trade_date = 20260529
scope_key = 20260529
```

精确清理本批 `stock_financial_metrics_fact`、quality、batch，并恢复 active `stock_financial` 到 `stock_financial_20260529_v1`。

本轮只提供 schema rollback：`sql/028_stock_financial_canonical_metrics_schema_rollback.sql`。

## N2 Handoff

N2 未来只读 active `stock_financial`，从 N1 透传 canonical fields 到条件层输出。N2 不得重算获现率、`pe_core`、同比、连续季度、forecast score、综合 score 或 warning。
