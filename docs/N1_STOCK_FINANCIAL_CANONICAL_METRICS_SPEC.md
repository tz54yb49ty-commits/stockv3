# N1 Stock Financial Canonical Metrics Spec

日期：2026-06-01
layer_role：N1_ingestion
状态：DESIGN_PASS draft，等待 028 migration final gate

## 目标

`stock_financial_metrics_fact` 是 v3 财务指标的 canonical 定稿表。N1 负责按 active `stock_financial` source_version 计算并定稿财务指标；N2 只能读取 active stock_financial source_version 并透传到 `stock_condition_basis`、`stock_condition_pool`、`stock_condition_display_basis`，N2 不得重算财务指标。

## 边界

本轮只做 spec、schema migration draft、rollback draft、dry-run contract 和测试草案。

不执行 migration，不写 `stock_financial_metrics_fact`，不写 `condition_*`，不进入 N2/N3/N4/N5/N6，不拉分钟 K，不启动 worker，不触碰旧系统写入。

## 数据源合同

1. Mootdx `affair` 全市场财务包是唯一财务主源；禁止逐股调用 `finance(symbol)`。
2. Tushare 仅调用 `daily_basic`，提供 `total_mv`、`circ_mv`、`pe_core`。
3. `forecast_vip`、`forecast()`、600588 PDF/override 均不属于本路径。

## As-Of 防未来函数

`source_trade_date = D` 时，财务快照只能使用 `announcement_date <= D` 的财报。

`announcement_date > D` 的财报必须排除，并计入 `asof_excluded_future_rows`。缺 `announcement_date` 且无法证明 as-of 安全的数据不得进入 canonical metrics，计入 `missing_announcement_date_excluded_rows` 或 P0/P1 质量项。

## Canonical 字段

已有字段继续承载：

- `pe_core`
- `score`
- `warning`
- `quality_status`
- `source_trade_date`
- `announcement_date`

028 迁移新增 nullable 字段：

- `cash_realization_rate`
- `revenue_yoy_pct`
- `core_profit_yoy_pct`
- `report_core_revenue`
- `report_core_profit`
- `core_profit_ttm`
- `core_gt_revenue_yoy`
- `revenue_growth_streak_q`
- `core_growth_streak_q`
- `core_gt_revenue_streak_q`
- `forecast_type`
- `forecast_score`
- `score_breakdown_json`
- `financial_warning_json`
- `financial_metric_version`

## 指标定义

### report_core_profit

`report_core_profit` 使用单季口径：

```text
单季营业收入
- 营业成本
- 税金及附加
- 销售费用
- 管理费用
- 研发费用
- 利息费用
```

如果利息费用缺失，使用财务费用替代，写入 `financial_warning_json`，quality 不得静默 passed。

### cash_realization_rate

```text
cash_realization_rate = 经营活动现金流 / report_core_profit
```

当 `report_core_profit <= 0` 或缺失时，`cash_realization_rate` 置空，并写 warning。

### core_profit_ttm 与 pe_core

```text
core_profit_ttm = 最近 4 个单季核心利润之和
```

Affair 权威路径不足 4 个连续单季时，`core_profit_ttm`、同比、连续季、
`pe_core` 和 `score` 中的相应项置 NULL 并记 P1，不再年化猜测。

```text
pe_core = Tushare total_mv(万元) * 10000 / core_profit_ttm(元)
```

`pe_core` 必须使用 `core_profit_ttm`，不得继续等同旧 `pe_ttm`。

### 同比与连续季度

`revenue_yoy_pct` 使用 Affair 本期单季营收与去年同期单季营收计算。

`core_profit_yoy_pct` 使用本期单季核心利润与去年同期单季核心利润计算。

```text
core_gt_revenue_yoy = core_profit_yoy_pct > revenue_yoy_pct
```

连续季度从最新报告期往前数：

- `revenue_growth_streak_q`：`revenue_yoy_pct > 0`
- `core_growth_streak_q`：`core_profit_yoy_pct > 0`
- `core_gt_revenue_streak_q`：`core_profit_yoy_pct > revenue_yoy_pct`

### Forecast 停用

Affair 权威路径固定 `forecast_type=NULL`、`forecast_score=NULL`，不调用
`forecast()` 或 `forecast_vip`。旧 snapshot 中的 Forecast 不得进入新 canonical 计算。

### score 有效满分封顶 97

`score` 有效满分封顶 97，`score_breakdown_json` 必须记录拆分来源：

- 核心利润为正：最多 +10
- 获现率：最多 +15
- PE_core：最多 +20
- 营收同比：最多 +10
- 核心同比：最多 +15
- 核心同比 > 营收同比：最多 +10
- 营收连增：最多 +5
- 核心连增：最多 +8
- 核心 > 营收连续：最多 +4
- Forecast 贡献：固定 0（字段保留为 NULL）

## Quality Gate

P0：

- as-of future row 未排除。
- 缺 `announcement_date` 且无法证明 as-of 安全却进入 canonical metrics。
- Affair 路径 `score` 超出 0-97。
- streak 小于 0。
- `financial_metric_version` 不合法。
- active source_version 冲突。

P1：

- 利息费用缺失并使用财务费用替代。
- TDX 缺失且使用 Tushare 兜底。
- TTM/同比所需的完整季度链不足，对应指标置 NULL。
- `daily_basic.total_mv` 缺失，只影响 `pe_core` 和 `score`。
- Affair 源失败、覆盖不足或单股财报不可用后执行 snapshot/NULL 降级。

P2：

- 非阻断性 coverage 说明、字段级 warning 分布和样本。

## Source Version 策略

继续使用：

```text
data_domain = stock
data_type = stock_financial
scope_key = 20260529
```

建议版本：

```text
source_batch_id = stock_financial_canonical_20260529_v1
source_version = stock_financial_20260529_v2
previous_source_version = stock_financial_20260529_v1
financial_metric_version = financial_metric_v1
```

激活：

```text
stock / stock_financial / 20260529 -> stock_financial_20260529_v2
```

## N2 承接

N2 后续只读 active `stock_financial` source_version，并把 canonical 字段透传到条件层表；不得在 N2 重新计算获现率、`pe_core`、同比、连续季度、forecast score、综合 score 或 warning。

N2 writer/readiness 后续需要单独 gate，不能在本轮进入。
# Mootdx affair financial-only path

The financial-only N1 source path is selected with `--financial-only` on the
source-bundle planner. It uses the newest ten usable quarterly Mootdx Affair
packages at or before `source_trade_date` and never calls `finance(symbol)`,
Tushare financial endpoints, `forecast_vip`, or `tushare.forecast`.
`stock_daily_basic` remains the only `total_mv` input; financial rows carry
`forecast_type=NULL` and `forecast_score=NULL`, while the score contribution
is zero and the effective score maximum is 97.

Affair values in the documented invalid-sentinel set are normalized to NULL.
Rows whose announcement date is missing or later than `source_trade_date` are
not accepted as fresh rows. Fresh coverage is the number of frozen-universe
identities with at least one accepted as-of row in the ten packages. At or
above 90%, fresh rows are used and missing/all-core-incomplete identities use
the previous snapshot; identities still without history receive one bounded
P1 NULL-warning row. Below 90%, or on manifest/TLS/download/parse failure, the
whole universe uses `previous_snapshot_full_carry_forward`; current-only
identities receive the same P1 NULL-warning row and previous-only identities
are removed. These availability failures must not block Fast Lane.

The default cache is `~/.cache/ashare_v3/mootdx_affair`. A complete local set
is selected before any network request and is verified by regular-file/no-
symlink checks, size, ZIP CRC and SHA-256. Files with size `<=1024` and future
quarters are excluded. The package manifest/SHA, fresh/carry/NULL counts and
hashes, final identity count/hash, degradation reason and
`financial_degraded_but_fastlane_allowed=true` are persisted in `source_probe`.
Final identity equality, duplicate identities, count/hash mismatch and DB
commit failure remain P0; source availability and per-stock coverage are P1.
Exact duplicate legacy rows are removed and recorded as P1. Same-grain
conflicts from an immutable previous snapshot keep the first persisted row and
record a bounded P1 manifest; the same conflict in fresh Affair rows remains
P0.
