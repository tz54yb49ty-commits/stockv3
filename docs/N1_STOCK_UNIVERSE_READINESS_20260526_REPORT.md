# N1 Stock Universe Readiness 20260526 Report

日期：2026-05-27
layer_role：`N1_ingestion`
状态：`READINESS_BLOCKED`

## Summary

```text
raw_active_universe = 5523
effective_active_universe = 5522
tushare_daily_matched = 5504
unresolved_daily_missing_active = 2
supplemental_source_available = 16
P0/P1/P2 = 2/17/0
```

## 19 Stock Disposition

| identity_key | name | Tushare daily | adj_factor | TDX/Mootdx daily | disposition | severity |
|---|---:|---:|---:|---:|---|---|
| stock:SZ:300114 | 中航成飞 | False | False |  | exclude_from_expected_universe | P1 |
| stock:BJ:920058 | 华洋赛车 | False | True | False | no_trade_candidate_without_official_proof | P0 |
| stock:BJ:920305 | *ST云创 | False | True | False | no_trade_candidate_without_official_proof | P0 |
| stock:SH:600193 | *ST创兴 | False | True | True | supplemental_source_bar | P1 |
| stock:SH:600421 | *ST华嵘 | False | True | True | supplemental_source_bar | P1 |
| stock:SH:600599 | *ST熊猫 | False | True | True | supplemental_source_bar | P1 |
| stock:SH:600608 | *ST沪科 | False | True | True | supplemental_source_bar | P1 |
| stock:SH:600636 | *ST国化 | False | True | True | supplemental_source_bar | P1 |
| stock:SH:600696 | *ST岩石 | False | True | True | supplemental_source_bar | P1 |
| stock:SH:605081 | *ST太和 | False | True | True | supplemental_source_bar | P1 |
| stock:SH:688121 | 卓然股份 | False | True | True | supplemental_source_bar | P1 |
| stock:SZ:000004 | *ST国华 | False | True | True | supplemental_source_bar | P1 |
| stock:SZ:000638 | *ST万方 | False | True | True | supplemental_source_bar | P1 |
| stock:SZ:002731 | ST萃华 | False | True | True | supplemental_source_bar | P1 |
| stock:SZ:002808 | *ST恒久 | False | True | True | supplemental_source_bar | P1 |
| stock:SZ:002898 | *ST赛隆 | False | True | True | supplemental_source_bar | P1 |
| stock:SZ:300029 | *ST天龙 | False | True | True | supplemental_source_bar | P1 |
| stock:SZ:300550 | 和仁科技 | False | True | True | supplemental_source_bar | P1 |
| stock:SZ:301096 | 百诚医药 | False | True | True | supplemental_source_bar | P1 |

## Boundary

不写 PostgreSQL、不写 Parquet、不改 active_source_version、不进入 N2-N6、不启动 worker。
