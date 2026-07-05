# N1 Stock Financial Canonical Metrics Spec

日期：2026-06-01
layer_role：N1_ingestion
状态：DESIGN_PASS draft，等待 028 migration final gate

## 目标

`stock_financial_metrics_fact` 是 v3 财务指标的 canonical 定稿表。N1 负责按 active `stock_financial` source_version 计算并定稿财务指标；N2 只能读取 active stock_financial source_version 并透传到 `stock_condition_basis`、`stock_condition_pool`、`stock_condition_display_basis`，N2 不得重算财务指标。

## 边界

本轮只做 spec、schema migration draft、rollback draft、dry-run contract 和测试草案。

不执行 migration，不写 `stock_financial_metrics_fact`，不写 `condition_*`，不进入 N2/N3/N4/N5/N6，不拉分钟 K，不启动 worker，不触碰旧系统写入。

## 数据源优先级

1. TDX/Mootdx 财务包优先。
2. Tushare 兜底。
3. Tushare 用于 `daily_basic.total_mv`、业绩预告 `forecast_type`、TDX 缺失股票的利润表/现金流兜底、as-of `announcement_date` 补充。

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

不足 4 个单季但有数据时：

```text
core_profit_ttm = 已有单季核心利润合计 * 4 / 已有季度数
```

```text
pe_core = total_mv / core_profit_ttm
```

`pe_core` 必须使用 `core_profit_ttm`，不得继续等同旧 `pe_ttm`。

### 同比与连续季度

`revenue_yoy_pct` 优先使用 TDX 财务包自带字段；缺失时使用本期单季营收与去年同期单季营收计算。

`core_profit_yoy_pct` 使用本期单季核心利润与去年同期单季核心利润计算。

```text
core_gt_revenue_yoy = core_profit_yoy_pct > revenue_yoy_pct
```

连续季度从最新报告期往前数：

- `revenue_growth_streak_q`：`revenue_yoy_pct > 0`
- `core_growth_streak_q`：`core_profit_yoy_pct > 0`
- `core_gt_revenue_streak_q`：`core_profit_yoy_pct > revenue_yoy_pct`

### forecast_score

```text
预增 / 扭亏 = +3
略增 = +2
续盈 = +1.5
略减 = +0.5
预减 / 首亏 / 续亏 = 0
```

### score 满分封顶 100

`score` 满分封顶 100，`score_breakdown_json` 必须记录拆分来源：

- 核心利润为正：最多 +10
- 获现率：最多 +15
- PE_core：最多 +20
- 营收同比：最多 +10
- 核心同比：最多 +15
- 核心同比 > 营收同比：最多 +10
- 营收连增：最多 +5
- 核心连增：最多 +8
- 核心 > 营收连续：最多 +4
- 业绩预告：最多 +3

## Quality Gate

P0：

- as-of future row 未排除。
- 缺 `announcement_date` 且无法证明 as-of 安全却进入 canonical metrics。
- `score` 超出 0-100。
- `forecast_score` 超出 0-3。
- streak 小于 0。
- `financial_metric_version` 不合法。
- active source_version 冲突。

P1：

- 利息费用缺失并使用财务费用替代。
- TDX 缺失且使用 Tushare 兜底。
- TTM 不足 4 季使用年化。
- forecast 缺失。

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
