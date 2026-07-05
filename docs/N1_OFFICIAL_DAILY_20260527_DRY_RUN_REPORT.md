# N1 Official Daily 20260527 Dry-Run Report

状态：`DRY_RUN_PASS`

本轮刷新只读复核 20260527 official daily 入库条件，不写 PostgreSQL，不写 Parquet，不改 active source_version，不进入 N2/N3/N4/N5/N6，不启动 worker，不触碰旧系统。

## Baseline

```text
trade_date = 20260527
calendar exists = true
is_open = true
prev_trade_date = 20260526
next_trade_date = 20260528
active trade_calendar = trade_calendar_20260527_patch_v1

stock_identity A_STOCK:20260527 = stock_identity_20260527_v1

stock_daily_bar_fact(20260527) = 0
index_daily_bar_fact(20260527) = 0
board_daily_bar_fact(20260527) = 0

20260527 daily active source_version = empty
batch/source_version/quality conflict = 0
```

## Identity Refresh

`stock_identity_refresh_required` 已解除。

```text
stock:SH:688635 / 688635.SH / 长进光子 / listed_date=20260527
stock:BJ:920161 / 920161.BJ / 龙辰科技 / listed_date=20260527
```

两只新股均已进入 20260527 expected stock universe，且 Tushare daily 5506 条均能映射到 `stock_identity`。

## Stock Scope

```text
stock_identity active universe = 5525
stale identity candidate = stock:SZ:300114
effective universe excluding stale = 5524

Tushare daily rows = 5506
Tushare daily rows with stock_identity = 5506
official_no_trade manifest = 18
supplemental_source_bar = 0
expected stock_daily_bar_fact rows = 5506
```

## Official No-Trade

18 只当前 effective universe 中未出现在 Tushare `daily`，但保留 official no-trade manifest，不写入 `stock_daily_bar_fact`。

```text
stock:BJ:920305
stock:SH:600193
stock:SH:600421
stock:SH:600599
stock:SH:600608
stock:SH:600636
stock:SH:600696
stock:SH:605081
stock:SH:688121
stock:SZ:000004
stock:SZ:000638
stock:SZ:002731
stock:SZ:002808
stock:SZ:002898
stock:SZ:300029
stock:SZ:300550
stock:SZ:300561
stock:SZ:301096
```

## Index Scope

沿用扩展口径：

```text
index_membership indices = 82
fixed 9 included = 9/9
expected index_daily_bar_fact rows = 83
expected Mootdx rows = 81
Tushare BJ fallback available = 2
UNKNOWN writes = 0
```

Canonical mapping 必须保留：

```text
index:UNKNOWN:899050 -> index:BJ:899050
index:UNKNOWN:899601 -> index:BJ:899601
```

## Board Scope

```text
expected board_daily_bar_fact rows = 428
881 industry required coverage = 127/127
```

## Expected Rows

```text
stock_daily_bar_fact = 5506
index_daily_bar_fact = 83
board_daily_bar_fact = 428
total = 6017
```

## Quality

```text
P0 = 0
P1 = 19
P2 = 0
```

P1 包括：

```text
stale_identity_excluded = 1
official_no_trade_manifest = 18
```

## Conclusion

20260527 official daily ingestion 数据预检已通过，`stock_identity_refresh_required` 不再阻断。由于 20260527 official daily execute runner 尚未实现，下一步应进入 N1 official daily 20260527 execute runner implementation，而不是直接 final execute。
