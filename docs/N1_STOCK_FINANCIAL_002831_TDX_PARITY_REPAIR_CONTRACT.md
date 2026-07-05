# N1 Stock Financial 002831 TDX Parity Repair Contract

Status: CONTRACT_PASS

## Scope

- layer_role=N1_ingestion
- source_trade_date=20260615
- repair identity=stock:SZ:002831 / 002831.SZ / 裕同科技
- current active source_version=stock_financial_20260615_v2
- target source_version=stock_financial_20260615_v3
- source_batch_id=stock_financial_002831_tdx_parity_repair_20260615_v1

Future execute write scope:
- stock_financial_metrics_fact
- common_ingest_batch
- common_quality_gate_result
- common_active_source_version

Forbidden:
- condition_* tables
- stock/index/board daily facts
- stock_daily_basic
- index_membership_fact / board_membership_fact
- outbox / inbox / checkpoint
- N2/N3/N4/N5/N6
- worker
- old system
- real trading

## Repair Contract

TDX/Mootdx financial package must be preferred over Tushare fallback.

For 002831:
- source_type must not be tushare_fallback
- interest_expense must be 19744658
- finance_expense=68186034.99 must not be used as interest_expense
- announcement_date must be present and <= 20260615
- report_period must be 20260331

Target metrics:
- report_core_profit=341586050
- operating_cashflow=657719040
- cash_realization_rate=1.9254856573
- core_profit_ttm=1940382164
- revenue_yoy_pct approximately 2.55
- core_profit_yoy_pct=57.1302091953
- core_gt_revenue_yoy=true
- revenue_growth_streak_q=9
- core_growth_streak_q=4
- core_gt_revenue_streak_q=2
- forecast_type=null
- score=87

core_profit_ttm must be the sum of these four single-quarter core profits:
- 20260331=341586050
- 20251231=509246816
- 20250930=735327224
- 20250630=354222074

pe_core must use total market value in yuan:
- daily_basic.total_mv=3929409.6385 ten-thousand yuan
- total_mv_yuan=39294096385
- pe_core=20.2506996374

## Source Version Policy

stock_financial_20260615_v3 must be a complete replacement source_version:
- expected rows=5504
- changed rows=1
- unchanged rows=5503

A one-row-only active stock_financial source_version is forbidden.

## Runner Requirements

Future execute runner must require:
- --execute
- --user-confirmed
- --postgres-commit-enabled

Runner must block before DB write if:
- source proof is missing
- target v3 rows already exist
- batch / quality / active source_version conflicts exist
- generated fact plan rows != 5504
- 002831 source_type is tushare_fallback
- interest_expense is missing
- finance_expense is used as interest_expense
- pe_core does not convert daily_basic total_mv from ten-thousand yuan to yuan
- announcement_date is missing or later than 20260615
- P0 > 0

## Source Proof And Runner

Source proof artifact:
- `docs/N1_STOCK_FINANCIAL_002831_TDX_FULL_LINE_ITEM_SOURCE_PROOF.json`

Runner:
- `scripts/run_stock_financial_002831_tdx_parity_repair_once.py`
- runner_readiness=ready_for_final_gate

Final execute gate review is allowed.
