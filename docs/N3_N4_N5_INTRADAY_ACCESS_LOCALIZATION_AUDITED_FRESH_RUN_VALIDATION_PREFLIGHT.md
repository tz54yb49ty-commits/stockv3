# N3/N4/N5 Intraday Access Localization Audited Fresh-Run Validation Preflight

Gate: `N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_PREFLIGHT_GATE`

Result: `PREFLIGHT_PASS`

Layer role: `runtime_control`

Generated on: `2026-06-07`

## Objective

Preflight the read-only audited fresh-run validation commands and acceptance checks for N3/N4/N5 intraday access localization.

This gate selects commands only. It does not execute the probe commands, write database rows, run migrations, consume outbox/inbox/checkpoint rows, start workers, or enter delivery, sim, position, PnL, real trade, proposal, order, or trade flows.

## Preflight Summary

- structured query audit closeout: `CLOSEOUT_PASS`
- fresh-run validation contract: `CONTRACT_PASS`
- selected probe commands: `3`
- probe execution in this gate: `false`
- allow enter audited fresh-run validation: `true`

## Static Coverage

| Scope | Direct `psycopg.connect` sites |
|---|---:|
| `src/ashare_v3/market` | 0 |
| `src/ashare_v3/trigger` | 0 |
| `src/ashare_v3/action` | 0 |
| `scripts` | 33 |

N3/N4/N5 runtime direct sites: `0`

Remaining scope: N1/N2/ingestion scripts only.

## Artifact Plan

Audit artifact directory:

```text
docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION
```

Report artifact directory:

```text
docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports
```

Source run id prefix:

```text
runtime_control_intraday_access_localization_validation_20260607
```

## Approved Probe Commands

### N3 Market Data

```bash
PYTHONPATH=src:scripts ASHARE_QUERY_AUDIT_DIR=docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION ASHARE_QUERY_AUDIT_SOURCE_RUN_ID=runtime_control_intraday_access_localization_validation_20260607_n3 python3 scripts/plan_n3_repaired_context_action_confirmation_metric_20260605.py --payload-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/n3_repaired_context_metric_payload.json --contract-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/n3_repaired_context_metric_contract.json --contract-md-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/n3_repaired_context_metric_contract.md --preflight-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/n3_repaired_context_metric_preflight.json --preflight-md-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/n3_repaired_context_metric_preflight.md --dry-run-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/n3_repaired_context_metric_dry_run.json --dry-run-md-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/n3_repaired_context_metric_dry_run.md --rollback-sql-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/n3_repaired_context_metric_rollback.sql
```

Allowed path role: `n3_readonly_plan`

### N4 Trigger

```bash
PYTHONPATH=src:scripts ASHARE_QUERY_AUDIT_DIR=docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION ASHARE_QUERY_AUDIT_SOURCE_RUN_ID=runtime_control_intraday_access_localization_validation_20260607_n4 python3 scripts/plan_n4_20260605_v4_corrected_dry_run.py --json-report-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/n4_v4_corrected_dry_run.json --markdown-report-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/n4_v4_corrected_dry_run.md --sample-limit 20
```

Allowed path role: `n4_readonly_plan`

### N5 Action

```bash
PYTHONPATH=src:scripts ASHARE_QUERY_AUDIT_DIR=docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION ASHARE_QUERY_AUDIT_SOURCE_RUN_ID=runtime_control_intraday_access_localization_validation_20260607_n5 python3 scripts/plan_action_preflight_dry_run.py --trigger-run-id trigger_execute_20260605_condition_layer_20260604_source_20260604_v1 --action-run-id runtime_control_intraday_access_localization_validation_20260607_n5_action_preflight --json-report-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/n5_action_preflight.json --markdown-report-path docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/n5_action_preflight.md --sample-limit 20
```

Allowed path role: `n5_readonly_plan`

## Command Policy Check

- forbidden flags absent: `true`
- `--execute` absent: `true`
- worker flags absent: `true`
- consume flags absent: `true`
- delivery/trade flags absent: `true`
- commands are read-only shape: `true`

## Pre/Post Snapshot Plan

Snapshot artifact path:

```text
docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION/reports/pre_post_snapshot.json
```

Required scopes:

- `common_event_outbox` status counts
- `common_event_inbox` scoped counts
- `common_event_consumer_checkpoint` scoped counts
- `common_trigger_match` scoped counts
- `common_trigger_state` scoped counts
- `common_action_event` scoped counts
- N6 projection/card/notification scoped counts when present

Acceptance: before snapshot equals after snapshot for all forbidden mutation scopes.

## Future Validation Acceptance

- All approved probe commands exit 0 or produce explicit non-P0 blocked reports while still emitting audit artifacts.
- Audit artifact directory exists and includes N3/N4/N5 artifacts.
- Every audit entry includes layer/source/stage/gate/application name/fingerprint/referenced tables/timestamps/duration/rowcount/side-effect flags.
- All read-only probe entries have `readonly_transaction=true`.
- `db_write_attempted_entries=0`.
- `worker_started_entries=0`.
- `outbox_consumed_entries=0`.
- `checkpoint_updated_entries=0`.
- `denied_table_hit_entries=0`.
- No referenced table includes the five denied display/membership tables.
- Pre/post forbidden mutation snapshots are identical.

## P0/P1/P2

`P0/P1/P2 = 0/2/0`

P1 items:

- Approved probe commands are selected but not executed in this preflight gate.
- 33 N1/N2/ingestion script direct connect sites remain outside this N3/N4/N5 validation scope.

## Forbidden Scope Proof

This preflight did not perform or authorize:

- DB writes or migrations
- probe command execution
- `pg_stat_statements` enablement
- PostgreSQL config changes
- worker startup
- outbox/inbox/checkpoint consumption or mutation
- delivery, push, voice, or mobile
- sim, position, PnL, or real trade
- proposal, order, or trade

## Next Gate Recommendation

`N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_EXECUTE_GATE`
