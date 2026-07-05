# N3/N4/N5 Intraday Access Localization Audited Fresh-Run Validation Recontract

Gate: `N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT_GATE`

Result: `CONTRACT_PASS`

Layer role: `runtime_control`

Generated at: `2026-06-07T04:50:26.117665+00:00`

## Objective

Replace stale execute-style probes with post-closeout read-only audit-only validation profiles. The validation target is SQL attribution and boundary proof, not N3 metric materialization readiness or N5 legacy candidate semantics.

## Lessons From Blocked Execute Gate

- N3: baseline-zero materialization preflight is stale because the projection run is already materialized and downstream-referenced.
- N4: artifact filename overflow has been hardened; the N4 read-only dry-run can be reused.
- N5: legacy `BUY_HINT/SELL_HINT` preservation preflight is not a valid P0 for access-localization validation under current full-metric-union lineage.

## Recontracted Probe Profiles

### N3

Use `existing_lineage_readonly_audit_probe` over current N3 metric lineage. It may read metric run/status/counts and event infra counts, but must not run materialization, require baseline zero, write metric rows, rollback, or read raw K / denied N2 tables.

### N4

Reuse hardened `plan_n4_20260605_v4_corrected_dry_run.py` without `--execute`. Expected shape: `DRY_RUN_PASS`, `compliant_count=605`, `blocked_count=291`, `execute_preflight_could_pass=true`.

### N5

Use `existing_lineage_readonly_audit_probe` over current N5 action/outbox metadata. It may read action run/event/outbox/status and downstream count proofs, but must not run legacy `BUY_HINT/SELL_HINT` readiness gate as access-localization P0, update metadata, consume outbox, or write N6 projection/card/UI.

## Acceptance Criteria

- Static coverage remains `market=0`, `trigger=0`, `action=0` direct `psycopg.connect` sites.
- N3/N4/N5 audit artifacts exist and parse.
- All entries are readonly and include attribution fields.
- Denied display/membership table references are `0`.
- `db_write_attempted=0`, `worker_started=0`, `outbox_consumed=0`, `checkpoint_updated=0`.
- Pre/post forbidden mutation snapshots are identical.
- No command contains execute/user-confirmed/consume/worker/delivery/trade/rollback/migration semantics.

## P0/P1/P2

`P0/P1/P2 = 0/2/0`

P1 items:

- 33 N1/N2/ingestion script direct connect sites remain documented outside N3/N4/N5 runtime scope.
- Next preflight must select or generate concrete N3/N5 audit-only probe commands.

## Forbidden Scope Proof

This recontract gate did not write database rows, run migrations, execute rollback SQL, enable `pg_stat_statements`, change PostgreSQL config, execute business runners, consume/update outbox/inbox/checkpoint, start workers, or enter delivery/push/voice/mobile/sim/position/PnL/real_trade/proposal/order/trade.

## Next Gate Recommendation

`N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT_PREFLIGHT_GATE`

## Validation Summary

- JSON parse: `PASS`
- structured query audit/adoption unittests: `23 OK`
- `git diff --check`: `PASS`
