# N1 Official Daily 20260526 V2 Ingestion Dry-Run Plan

日期：2026-05-27
layer_role：`N1_ingestion`
状态：`DRY_RUN_PASS`

## Scope

```text
trade_date = 20260526
source_batch_id = official_daily_ingest_20260526_v2
stock source_version = stock_daily_20260526_v2
index source_version = index_daily_20260526_v2
board source_version = board_daily_20260526_v2
```

## Expected Rows

```text
stock_daily_bar_fact expected = 5520
  Tushare daily + adj_factor = 5504
  TDX/Mootdx supplemental stock bars = 16
index_daily_bar_fact expected = 9
board_daily_bar_fact expected = 428
total daily fact expected = 5957
```

Stock universe scope:

```text
raw_active_universe = 5523
stale_identity_excluded = 1
effective_active_universe = 5522
official_no_trade_manifest = 2
expected_stock_daily_bar_rows = 5520
```

## Stale Identity Manifest

| identity_key | disposition | proof |
|---|---|---|
| `stock:SZ:300114` | `exclude_from_expected_universe` | local identity is stale; current Tushare identity is `stock:SZ:302132` 中航成飞 |

## Official No-Trade Manifest

These rows are not written to `stock_daily_bar_fact` because the current table requires non-null OHLC and has no `official_daily_status` / `source_proof_json` columns.

| identity_key | name | proof | disposition |
|---|---|---|---|
| `stock:BJ:920058` | 华洋赛车 | Tushare `suspend_d` has `20260526` `suspend_type=S`; `bak_daily` has zero volume/amount state row | `official_no_trade` |
| `stock:BJ:920305` | *ST云创 | Tushare `suspend_d` has `20260526` `suspend_type=S`; `bak_daily` has zero volume/amount state row | `official_no_trade` |

## Supplemental Source Manifest

16 stocks missing from Tushare daily have TDX/Mootdx daily bar evidence and may enter `stock_daily_bar_fact` in v2 as supplemental stock bars. Execute must capture the raw TDX/Mootdx payload in `raw_payload` and quality details.

```text
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
stock:SZ:301096
```

## Quality Policy

```text
unresolved_source_gap = 0 required
duplicate identity_key = 0 required
same-code contamination = 0 required
stock adj_factor proof required for 5504 Tushare daily rows
supplemental source bars require source_proof_json
official_no_trade rows are manifest-only, not stock_daily_bar_fact rows
P0/P1/P2 = 0/19/0 expected before execute
```

## Boundary

This plan does not execute ingestion, fetch market data, write PostgreSQL, write Parquet, update active source versions, enter N2-N6, touch the old system, start workers, or perform real trading.
