# N1 20260608 Source Facts Guarded Runner Preflight

Result: `PREFLIGHT_PASS`

Policy result: `POLICY_PASS`

Contract result: `CONTRACT_PASS`

Execute authorized: `false`

Final execute gate review allowed: `true`

This gate was read-only. It did not execute, write PostgreSQL, run rollback SQL, enter N2-N6, consume outbox/inbox/checkpoint, start a worker, pull realtime quotes, touch old system, or touch proposal/order/trade/sim/position/PnL/real trade.

## Source And Date Proof

- target DB: `ashare_v3` / `ashare_v3_user` / `127.0.0.1:5432`
- transaction mode for the probe: `read_only=on`
- `for_trade_date=20260609`
- `source_trade_date=20260608`
- `20260608`: open, prev=`20260605`, next=`20260609`
- `20260609`: open, prev=`20260608`, next=`20260610`

## Source Probe

Stock:

- Tushare daily: `5515`
- adj_factor: `5527`
- daily_basic: `5515`
- matched identity: `5514`
- unmapped: `1`
- unmapped ts_code: `920206.BJ`
- duplicate daily ts_code: `0`
- duplicate daily_basic ts_code: `0`
- official no-trade candidate: `12`

Index:

- expected: `83`
- Mootdx expected: `81`
- Tushare BJ fallback expected: `2`

Board:

- expected: `428`

## Skip Policy

`skip_missing_stock_identity_when_count_lte_10`

- applies only to stock source rows
- threshold: `10`
- current missing count: `1`
- skipped identity: `stock:BJ:920206 / 920206.BJ`
- severity: `P1`
- stock daily fact write: `false`
- stock_daily_basic write: `false`
- stock_financial_metrics_fact write: `false`
- index/board missing identity remains `P0`
- fixed 9 index missing identity/source remains `P0`

## Baseline

- `stock_daily_bar_fact=0`
- `index_daily_bar_fact=0`
- `board_daily_bar_fact=0`
- `stock_daily_basic=0`
- `stock_financial_metrics_fact=0`
- `index_membership_fact=0`
- `board_membership_fact=0`
- batch conflicts: `0`
- quality conflicts: `0`
- active source_version conflicts: `0`

Current active stock identity scope:

- `A_STOCK:20260605 -> stock_identity_20260605_v1`
- active identity count: `5527`

Outbox/inbox/checkpoint snapshot:

- `198825 / 98564 / 7338`

## Adjusted Expected Rows

Official daily:

- `stock_daily_bar_fact=5514`
- `index_daily_bar_fact=83`
- `board_daily_bar_fact=428`
- `total_daily_fact=6025`

Condition source:

- `stock_daily_basic=5514`
- `stock_financial_metrics_fact=5514`
- `index_membership_fact=12841`
- `board_membership_fact=56962`
- `total_condition_source_fact=80831`

Combined total: `86856`.

Before policy, stock source rows were `5515`; `920206.BJ` is the single quality-visible exclusion.

## P0/P1/P2

- `P0=0`
- `P1=3`
- `P2=0`

P1:

- `missing_stock_identity_skip_policy_applied`: `920206.BJ` skipped, fact writes=false.
- `official_no_trade_manifest_candidate=12`; quality/details only, no stock daily fact write.
- Existing 20260608 runtime lineage from `source_trade_date=20260605` is orthogonal and excluded from this repair rollback scope.

## Planned Write Scope

Future execute may write only:

- `common_ingest_batch`
- `common_quality_gate_result`
- `common_active_source_version`
- `stock_daily_bar_fact`
- `index_daily_bar_fact`
- `board_daily_bar_fact`
- `stock_daily_basic`
- `stock_financial_metrics_fact`
- `index_membership_fact`
- `board_membership_fact`

It must not write:

- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- `condition_*`
- N2/N3/N4/N5/N6 runtime or fact tables
- Parquet
- old system files or services
- proposal/order/trade/sim/position/PnL/real trade

## Rollback

Rollback draft:

`sql/N1_20260608_source_facts_guarded_runner_rollback.sql`

Static contract:

- hard-fail before first `DELETE`
- scoped by `source_batch_id`, `source_version`, and `trade_date=20260608`
- no broad rollback by `for_trade_date=20260608`
- no `DROP`, `TRUNCATE`, or `CASCADE`
- no outbox/inbox/checkpoint DML
- no N2/N3/N4/N5/N6 DML

## Runner Readiness

`guarded_runner_implemented_policy_pass`

## Blockers

None.

## Next Gate

Allowed review gate:

`N1_20260608_SOURCE_FACTS_EXECUTE_FINAL_GATE_REVIEW`

Do not execute from this policy gate.
