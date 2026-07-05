# N2-R Index Golden Regression Report

日期：2026-05-24

范围：

```text
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
```

边界：

```text
只读 v3 开发库。
只读参考目标机 /Users/chuanfuchen/stock_monitor_isolated/data/monitor.db 的 signal_precompute_cache。
未写 v3 condition_basis / condition_pool / minute_target_scope。
未执行 migration。
未拉行情 / 分钟 K。
未进入 N3 / trigger / action / mobile / voice / sim / worker。
```

## 1. 修复口径

N2-R 已把 condition_basis 周期口径调整为：

```text
1. 非 D 周期分级金额比较使用 avg_amount，不使用 sum(amount)。
2. 价格方向比较使用上一周期实体上沿/下沿：
   close_now > max(open_prev, close_prev) -> 上涨类
   close_now < min(open_prev, close_prev) -> 下跌类
   其余 -> flat
3. period_transition 不再硬等于 period_grade。
4. prev_up_str / prev_dn_str 基于 transition 生成固定 5 位位置串。
5. Hint 必要条件按最小趋势周期以下小周期全弱/全强判断，不再用 any(UP/DOWN)。
6. 固定 9 指数默认策略改为 exchange-qualified identity。
```

## 2. Golden 对比

目标机 golden 来源：

```text
/Users/chuanfuchen/stock_monitor_isolated/data/monitor.db
signal_precompute_cache
trade_date = 20260525
monitor_type = index
```

v3 dry-run 来源：

```text
scripts/build_condition_basis.py --source-trade-date 20260522 --dry-run
scripts/build_condition_pool.py --source-trade-date 20260522 --dry-run
```

说明：全量 JSON dry-run 报告只作为本轮临时核对文件生成，因包含全量 stock/index/board basis/pool 行，体积较大，最终不保留；本文件保留 9 指数 golden 摘要和阻断结论。

| code | identity | v3 basis | prev_up_str | prev_dn_str | BUY key | SELL key | transition Y/Q/M/W/D | 对比 |
|---|---|---:|---|---|---|---|---|---|
| 000905 | index:SH:000905 | yes | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D | volume_up / volume_up / volume_up / flat / flat | match |
| 399303 | index:SZ:399303 | yes | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D | volume_up / volume_up / volume_up / flat / flat | match |
| 000001 | index:SH:000001 | no | - | - | - | - | - | P0 missing basis |
| 000852 | index:SH:000852 | yes | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D | volume_up / volume_up / volume_up / flat / flat | match |
| 399001 | index:SZ:399001 | yes | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D | volume_up / volume_up / volume_up / flat / flat | match |
| 399006 | index:SZ:399006 | yes | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D | volume_up / volume_up / volume_up / low_volume_up / flat | match |
| 000300 | index:SH:000300 | yes | YQM-- | ---w- | BUY:W,D | SELL:Y,Q,M,D | volume_up / volume_up / volume_up / low_volume_down / flat | match |
| 000016 | index:SH:000016 | yes | ----- | ---w- | BUY:Y,Q,M,W,D | SELL:Y,Q,M,D | flat / flat / flat / low_volume_down / flat | match |
| 000688 | index:SH:000688 | yes | YQMW- | ----- | BUY:D | SELL:Y,Q,M,W,D | volume_up / volume_up / volume_up / volume_up / flat | match |

结论：

```text
已入库的 8 个固定指数与目标机 golden 口径一致。
000001.SH 在 v3 active index_daily source 中缺少 index_condition_basis 来源，已作为 P0 阻断。
```

## 3. Dry-run 摘要

condition_basis dry-run：

```text
stock_rows = 5504
index_rows = 80
board_rows = 428
p0_count = 1
p1_count = 3
p2_count = 1
```

P0：

```text
fixed_9_index_basis_coverage failed
missing_identity_keys = [index:SH:000001]
```

condition_pool dry-run：

```text
stock_pool_rows = 4236
index_pool_rows = 16
board_pool_rows = 258
p0_count = 1
```

说明：

```text
index_pool_rows = 16 是 8 个已入库固定指数 * buy/sell 条件来源行。
000001.SH 缺 basis，因此不会进入 pool/scope。
pool 已继承 basis P0，不允许进入 execute/overwrite。
```

## 4. 后续处理

阻断项归属：

```text
000001.SH index_daily_bar_fact / active source_version 缺口属于入库层修复。
条件层不得硬造 index:SH:000001 basis，也不得在 pool/scope 静默跳过。
```

下一步建议：

```text
1. 入库层补齐 20260522 active index_daily source 中的 000001.SH。
2. 重跑 N2-R basis/pool dry-run。
3. 只有 fixed_9_index_basis_coverage P0=0 后，才允许重新做 condition_pool / minute_target_scope execute preflight。
```
