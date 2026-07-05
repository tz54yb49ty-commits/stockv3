# N1 Stock Financial 002831 TDX Parity Repair Dry Run

Result: DRY_RUN_PASS

Scope:
- layer_role=N1_ingestion
- source_trade_date=20260615
- current active source_version=stock_financial_20260615_v2
- target source_version=stock_financial_20260615_v3
- target source_batch_id=stock_financial_002831_tdx_parity_repair_20260615_v1

## Current Evidence

DB baseline:
- active stock_financial 20260615 = stock_financial_20260615_v2
- stock_financial_20260615_v1 rows = 5504
- stock_financial_20260615_v2 rows = 5504
- stock_financial_20260615_v3 rows = 0
- target batch / quality / active conflicts = 0 / 0 / 0

002831 identity:
- stock_identity_key=stock:SZ:002831
- ts_code=002831.SZ
- name=裕同科技
- industry=广告包装

Current v2 row:
- source=stock_financial_canonical.tdx_mootdx_first.tushare_fallback
- latest_source_type=tushare_fallback
- report_period=20260331
- announcement_date=20260428
- report_core_profit=293144510.81
- operating_cashflow=657719031.03
- cash_realization_rate=2.2436682482
- core_profit_ttm=4188193627.27
- pe_core=0.0009382111
- core_profit_yoy_pct=15.7585516772
- core_growth_streak_q=1
- core_gt_revenue_streak_q=0
- score=65.6617734382
- warning=forecast_missing;interest_expense_missing_finance_expense_used;tushare_fallback_used

Root cause:
- current v2 fell back to Tushare for 002831
- current v2 lacks interest_expense and used finance_expense=68186034.99
- pe_core used total_mv in daily_basic units of ten-thousand yuan without converting to yuan

## Target Parity Values

The target parity row must use TDX financial package line items:
- report_period=20260331
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

TTM proof:
- 20260331 = 341586050
- 20251231 = 509246816
- 20250930 = 735327224
- 20250630 = 354222074
- sum = 1940382164

PE proof:
- daily_basic.total_mv=3929409.6385, unit=ten-thousand yuan
- total_mv_yuan=39294096385
- pe_core=39294096385 / 1940382164 = 20.2506996374

## Source Proof Status

PASS:
- TDX full line-item proof is captured in `docs/N1_STOCK_FINANCIAL_002831_TDX_FULL_LINE_ITEM_SOURCE_PROOF.json`.
- The proof artifact records source_type=tdx_financial_package, report_period=20260331, announcement_date=20260428, and interest_expense=19744658.
- as-of rule passes because 20260428 <= 20260615.

Notes:
- The live Mootdx finance adapter still returns only a summary row and is not sufficient by itself.
- The inspected local TDX root still has no discoverable financial package file; this gate uses the scoped local source-proof artifact.

## Dry Run Plan

Future repair must build a complete replacement source_version:
- stock_financial_20260615_v3 expected rows = 5504
- changed financial rows count = 1
- unchanged rows copied or rebuilt from v2 = 5503
- active source_version is not changed in this gate

One-row-only active source_version is not allowed; v3 must be complete for 20260615.

## Quality

P0/P1/P2 = 0/1/0

P1:
- scoped parity repair for stock:SZ:002831 only.

## Boundary

No PostgreSQL writes were performed.
No active source_version was changed.
No condition source, N2, N3, N4, N5, N6, outbox, inbox, checkpoint, worker, old system, or real trading scope was touched.

Rollback draft:
- sql/N1_stock_financial_002831_tdx_parity_repair_20260615_rollback.sql

Runner:
- `scripts/run_stock_financial_002831_tdx_parity_repair_once.py`
- non-execute live preflight built full v3 plan rows=5504, changed rows=1, conflicts=0.

Final execute gate:
- Allowed to enter `N1_STOCK_FINANCIAL_002831_TDX_PARITY_REPAIR_FINAL_GATE_REVIEW`.
