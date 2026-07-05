# N2-R Golden Recheck Report

日期：2026-05-24

范围：

```text
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
```

边界：

```text
只在 v3 项目内工作。
未写 condition_basis / condition_pool / minute_target_scope。
未执行 overwrite。
未执行 migration。
未拉行情 / 分钟 K。
未进入 N3 / trigger / action / mobile / voice / sim / worker。
本轮未读取或写入旧系统数据库；golden 期望值使用 v3 测试中已固化的 N2-R regression。
```

## 1. Source Ready

```text
source_ready_passed = true
index_daily_active_source_version = index_daily_20260522_v2
index_daily_row_count = 81
index_daily_missing_identity_key_count = 0
missing_data_types = []
```

说明：

```text
入库层已把 000001.SH / index:SH:000001 补入 active index_daily v2。
```

## 2. Dry-run 结果

condition_basis dry-run：

```text
stock_rows = 5504
index_rows = 81
board_rows = 428
basis_p0_count = 1
basis_p1_count = 3
basis_p2_count = 1
```

condition_pool dry-run：

```text
stock_pool_rows = 4236
index_pool_rows = 16
board_pool_rows = 258
pool_p0_count = 1
pool_p1_count = 1
pool_p2_count = 1
```

P0：

```text
fixed_9_index_amount_baseline_coverage failed
warning_identity = index:SH:000001
```

## 3. 9 指数 Golden 对比

| code | identity | has_basis | amount_quality | prev_up_str | prev_dn_str | BUY key | SELL key | transition Y/Q/M/W/D | golden |
|---|---|---:|---|---|---|---|---|---|---|
| 000905 | index:SH:000905 | yes | passed | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D | volume_up / volume_up / volume_up / flat / flat | match |
| 399303 | index:SZ:399303 | yes | passed | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D | volume_up / volume_up / volume_up / flat / flat | match |
| 000001 | index:SH:000001 | yes | warning | ----- | ----- | - | - | unknown / unknown / unknown / unknown / unknown | DIFF |
| 000852 | index:SH:000852 | yes | passed | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D | volume_up / volume_up / volume_up / flat / flat | match |
| 399001 | index:SZ:399001 | yes | passed | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D | volume_up / volume_up / volume_up / flat / flat | match |
| 399006 | index:SZ:399006 | yes | passed | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D | volume_up / volume_up / volume_up / low_volume_up / flat | match |
| 000300 | index:SH:000300 | yes | passed | YQM-- | ---w- | BUY:W,D | SELL:Y,Q,M,D | volume_up / volume_up / volume_up / low_volume_down / flat | match |
| 000016 | index:SH:000016 | yes | passed | ----- | ---w- | BUY:Y,Q,M,W,D | SELL:Y,Q,M,D | flat / flat / flat / low_volume_down / flat | match |
| 000688 | index:SH:000688 | yes | passed | YQMW- | ----- | BUY:D | SELL:Y,Q,M,W,D | volume_up / volume_up / volume_up / volume_up / flat | match |

结论：

```text
固定 9 指数全部 has_basis=true。
其中 8 个指数与 golden 完全一致。
000001.SH 仍未对齐 golden：period_transition 全 unknown，BUY/SELL key 为空，未进入 index_condition_pool。
```

## 4. 000001.SH 差异原因

只读检查 v3 index_daily_bar_fact：

```text
index:SH:000001
source_version = index_daily_20260522_v2
row_count = 1
min_date = 20260522
max_date = 20260522
```

condition_basis 中 000001.SH：

```text
amount_quality_status = warning
amount_prev_day = null
amount_prev_week = null
amount_prev_month = null
amount_prev_quarter = null
amount_prev_year = null
prev_up_str = -----
prev_dn_str = -----
buy_necessary_key = null
sell_necessary_key = null
```

判断：

```text
入库层已经补齐 000001.SH 当日 fact，因此 has_basis=true。
但 000001.SH 缺少条件层分级所需的历史 index_daily_bar_fact。
条件层无法计算 Y/Q/M/W/D transition，也不能生成可信 condition_pool。
```

## 5. 本轮修正

本轮把固定 9 指数的 amount baseline 完整性升级为 P0：

```text
任一固定指数 amount_quality_status != passed
-> fixed_9_index_amount_baseline_coverage failed
-> condition_pool 继承 basis P0
-> 禁止 execute / overwrite
```

这样避免出现：

```text
000001.SH 有 basis 行，但 transition 全 unknown，pool 仍被误认为可通过。
```

## 6. 后续处理

下一步仍应回到入库层补齐 000001.SH 的历史 index_daily_bar_fact：

```text
至少需要覆盖上一交易日、上一周、上一月、上一季度、上一年度周期比较窗口。
补齐后重新激活 index_daily source_version。
再重跑 N2-R ready / basis / pool / golden regression。
```

本轮不允许进入：

```text
N2-E10 overwrite
N3 实时行情层
trigger / action / mobile / voice / sim / worker
```
