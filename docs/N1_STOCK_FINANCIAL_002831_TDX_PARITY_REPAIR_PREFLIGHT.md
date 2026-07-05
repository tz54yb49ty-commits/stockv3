# N1 Stock Financial 002831 TDX Parity Repair Preflight

Result: PREFLIGHT_PASS

## Baseline

- active source_version: stock_financial_20260615_v2
- active source_batch_id: stock_financial_canonical_20260615_v1
- target source_version: stock_financial_20260615_v3
- target source_batch_id: stock_financial_002831_tdx_parity_repair_20260615_v1
- target v3 fact rows: 0
- batch conflicts: 0
- quality conflicts: 0
- active conflicts: 0

## Expected Repair

- expected stock_financial_20260615_v3 rows: 5504
- changed financial rows count: 1
- target identity: stock:SZ:002831
- target report_period: 20260331
- target source: TDX财务包

## P0/P1/P2

P0/P1/P2 = 0/1/0

P0 blockers:
- none

P1 warnings:
- scoped_parity_repair_one_identity

P2:
- none

## Rollback

Rollback SQL draft:
- sql/N1_stock_financial_002831_tdx_parity_repair_20260615_rollback.sql

Rollback scope:
- delete only stock_financial_20260615_v3 rows from source_batch_id=stock_financial_002831_tdx_parity_repair_20260615_v1
- delete scoped quality and batch rows
- restore active stock_financial 20260615 to stock_financial_20260615_v2
- no condition_* DML
- no N2-N6 DML
- no outbox/inbox/checkpoint DML

The SQL has a hard-fail guard before destructive statements.

## Execute Gate Decision

Execute final gate review is allowed.

Execute command candidate:

```bash
PYTHONPATH=src python3 scripts/run_stock_financial_002831_tdx_parity_repair_once.py \
  --source-trade-date 20260615 \
  --stock-identity-key stock:SZ:002831 \
  --previous-source-version stock_financial_20260615_v2 \
  --target-source-version stock_financial_20260615_v3 \
  --execute \
  --user-confirmed \
  --postgres-commit-enabled \
  --json-report-path docs/N1_stock_financial_002831_tdx_parity_repair_execute_report.json \
  --markdown-report-path docs/N1_STOCK_FINANCIAL_002831_TDX_PARITY_REPAIR_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N1_stock_financial_002831_tdx_parity_repair_20260615_rollback.sql
```
