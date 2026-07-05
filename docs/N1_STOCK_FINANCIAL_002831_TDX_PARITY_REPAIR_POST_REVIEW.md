# N1 Stock Financial 002831 TDX Parity Repair Post Review

Result: `POST_REVIEW_PASS`

## Scope

- layer_role: `N1_ingestion`
- source_trade_date: `20260615`
- stock_identity_key: `stock:SZ:002831`
- source_batch_id: `stock_financial_002831_tdx_parity_repair_20260615_v1`
- previous_source_version: `stock_financial_20260615_v2`
- target_source_version: `stock_financial_20260615_v3`

## Execute Proof

- execute report JSON: `docs/N1_stock_financial_002831_tdx_parity_repair_execute_report.json`
- execute report MD: `docs/N1_STOCK_FINANCIAL_002831_TDX_PARITY_REPAIR_EXECUTE_REPORT.md`
- execute report JSON parse: `PASS`
- observed command exit code: `0`
- execute result: `EXECUTE_PASS`

## Row Count Proof

- `stock_financial_20260615_v3` fact rows: `5504`
- `stock_financial_20260615_v2` fact rows preserved: `5504`
- v3 batch rows: `1`
- v3 quality rows: `4`
- changed rows: `1`
- changed identity: `stock:SZ:002831`

## Active Source Proof

- active v3 rows: `1`
- active v2 rows: `0`
- active state: `stock_financial_20260615_v3_active`

## 002831 Target Row Proof

- source type: `tdx_financial_package`
- report_period: `20260331`
- announcement_date: `20260428`
- interest_expense: `19744658`
- finance_expense_used_as_interest: `false`
- operating_cashflow: `657719040`
- report_core_profit: `341586050`
- core_profit_ttm: `1940382164`
- pe_core: `20.2506996374`
- score: `87`

## Quality

- P0 failed: `0`
- P0 passed: `3`
- P1 warning: `1`
- P2 failed/warning: `0`

## Boundary Proof

- allowed write tables:
  - `stock_financial_metrics_fact`
  - `common_ingest_batch`
  - `common_quality_gate_result`
  - `common_active_source_version`
- outbox/inbox/checkpoint delta: `0/0/0`
- outbox/inbox/checkpoint refs to v3: `0/0/0`
- structured downstream N2-N6 refs to v3: `0`
- N2/N3/N4/N5/N6 entered: `false`
- worker_started: `false`
- Parquet written: `false`
- old system touched: `false`
- real trading: `false`

## Rollback Proof

- rollback SQL: `sql/N1_stock_financial_002831_tdx_parity_repair_20260615_rollback.sql`
- rollback executed: `false`
- hard-fail before first DELETE/UPDATE: `true`
- restores active source to v2 if authorized later: `true`
- downstream refs guard: `true`
- DROP/TRUNCATE/CASCADE absent: `true`

## Decision

N1 002831 TDX parity repair can be marked complete.

Next gate must be separate:

`N2_CONDITION_SOURCE_REFRESH_FOR_STOCK_FINANCIAL_20260615_V3_READINESS_GATE`
