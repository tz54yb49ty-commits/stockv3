# N3_N4_N5_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION_CONTRACT_GATE

Result: **CONTRACT_PASS**

Layer role: `runtime_control`

This contract defines the implementation plan for a structured query audit wrapper for N3/N4/N5 intraday table-access attribution. It does not implement code, write DB rows, enable `pg_stat_statements`, change PostgreSQL config, run migrations, consume/update outbox/inbox/checkpoint, start workers, or enter delivery/push/voice/mobile/sim/position/PnL/real trade/proposal/order/trade.

## Inputs

- `docs/N3_N4_N5_INTRADAY_ACCESS_OBSERVABILITY_CONTRACT.md`
- `docs/N3_N4_N5_INTRADAY_ACCESS_OBSERVABILITY_CONTRACT.json`
- `docs/N3_N4_N5_INTRADAY_ACCESS_OBSERVABILITY_DRY_RUN.md`
- `docs/N3_N4_N5_INTRADAY_ACCESS_OBSERVABILITY_DRY_RUN.json`
- `docs/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_REMEDIATION_CONTRACT.md`
- `docs/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_REMEDIATION_CONTRACT.json`
- `docs/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_REMEDIATION_DRY_RUN.md`
- `docs/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_REMEDIATION_DRY_RUN.json`

## Current State

- Observability contract: `CONTRACT_PASS`
- Recommended primary path: OBS-B structured query audit wrapper
- Interim path: OBS-C fresh-run read-only probe
- `pg_stat_statements`: available but not installed/enabled
- `application_name`: visible in `pg_stat_activity`
- `pg_stat_user_tables`: available
- query audit helper / audit sink: absent
- N3/N4/N5 `application_name` tagging matches: 0
- observability dry-run P0/P1/P2: `1 / 2 / 1`

## Wrapper Design

The wrapper must be artifact-first:

- initial audit sink is docs JSON or stdout captured by a later runner
- DB audit table creation is not authorized in this contract
- audit records must be emitted without writing business data

Proposed module:

`src/ashare_v3/observability/query_audit.py`

Proposed API:

- `AuditContext(layer_role, source_run_id, stage_id, gate_id, path_role, readonly_expected)`
- `build_application_name(context) -> str`
- `fingerprint_sql(sql_text) -> str`
- `extract_referenced_tables(sql_text) -> list[str]`
- `classify_statement_kind(sql_text) -> str`
- `assert_no_denied_tables(context, sql_text)`
- `audit_execute(cur, sql_text, params, context, sink) -> result`

Captured fields:

- `audit_event_id`
- `audit_run_id`
- `layer_role`
- `source_run_id`
- `stage_id`
- `gate_id`
- `path_role`
- `application_name`
- `statement_kind`
- `statement_fingerprint`
- `referenced_tables`
- `denied_table_hit`
- `started_at`
- `finished_at`
- `duration_ms`
- `rowcount`
- `readonly_transaction`
- `worker_started`
- `outbox_consumed`
- `checkpoint_updated`
- `db_write_attempted`
- `bypass_classification`

Side-effect flags:

- `worker_started`
- `outbox_consumed`
- `checkpoint_updated`
- `db_write_attempted`

## Denylist Policy

N3/N4/N5 intraday worker/execute paths must block before DB execution if SQL references:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

Denied path roles:

- `n3_intraday_worker`
- `n3_intraday_execute`
- `n4_intraday_worker`
- `n4_intraday_execute`
- `n5_intraday_worker`
- `n5_intraday_execute`

Allowed explicit bypass:

- `n4_one_time_context_refresh`
- must carry tag `one_time_context_refresh`
- may only read approved N2 basis/pool/scope or condition context enrichment sources

Unclassified bypass must fail closed.

## Coverage Plan

Must cover or explicitly classify:

- `src/ashare_v3/market/*`
- `src/ashare_v3/trigger/*`
- `src/ashare_v3/action/*`
- `scripts/run_*` and `scripts/plan_*` entries that invoke N3/N4/N5 paths

Current static inventory:

| scope | direct `psycopg.connect` occurrences | unique files |
|---|---:|---:|
| `src/ashare_v3/market` | 70 | 32 |
| `src/ashare_v3/trigger` | 43 | 14 |
| `src/ashare_v3/action` | 8 | 7 |
| `scripts` | 43 | 37 |
| total | 164 | 90 |

High-density first-pass files:

- `src/ashare_v3/trigger/context_execute.py`
- `src/ashare_v3/trigger/c3_replay_audit_execute.py`
- `src/ashare_v3/market/previous_day_preload_execute.py`
- `src/ashare_v3/market/action_confirmation_metric_materialization_execute.py`
- `src/ashare_v3/market/today_minute_execute.py`
- `src/ashare_v3/market/realtime_snapshot_execute.py`
- `src/ashare_v3/trigger/run_once_execute.py`
- `src/ashare_v3/trigger/local_trigger_dry_run.py`
- `src/ashare_v3/market/previous_day_full_context_expansion_subscription_scope.py`
- `src/ashare_v3/market/eod_snapshot_execute.py`
- `src/ashare_v3/market/closed_30m_replay_execute.py`
- `scripts/plan_n4_trigger_rule_v4_full_lineage_dry_run.py`

Classification states:

- `must_wrap`
- `explicit_bypass_readonly_plan`
- `explicit_bypass_one_time_context_refresh`
- `out_of_scope_n1_n2_or_migration`
- `blocked_until_refactored`

## Test Plan

Required tests:

- SQL extractor unit tests
- denylist guard tests
- application_name builder tests
- artifact sink JSON schema tests
- read-only no-side-effect tests
- static route/path scan
- regression: denied table SQL must BLOCK before execution

Proposed files:

- `tests/test_structured_query_audit.py`
- `tests/test_structured_query_audit_static_coverage.py`

Validation commands for a later implementation gate:

```bash
python3 -m unittest tests/test_structured_query_audit.py
python3 -m unittest tests/test_structured_query_audit_static_coverage.py
python3 -m compileall src/ashare_v3/observability src/ashare_v3/market src/ashare_v3/trigger src/ashare_v3/action scripts
python3 -m json.tool docs/N3_N4_N5_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION_REPORT.json >/dev/null
git diff --check
```

## Acceptance Criteria

- static scan finds no unclassified N3/N4/N5 `psycopg` connection sites
- all audited entries include layer/run_id/stage/gate_id/application_name
- denied table reference blocks before DB execution
- artifact sink can emit JSON without DB write
- dry-run can prove `worker_started=false` and outbox/inbox/checkpoint unchanged
- no N3/N4/N5 fact mutation
- N4 one-time context refresh bypass is explicit, audited, and limited to approved sources
- JSON parse, targeted tests, static coverage scan, compileall, and `git diff --check` pass

## Required Follow-Up Gates

- `N3_N4_N5_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION_GATE`
- `N3_N4_N5_STRUCTURED_QUERY_AUDIT_POST_REVIEW_GATE`
- `N3_N4_N5_INTRADAY_ACCESS_FRESH_RUN_PROBE_CONTRACT_GATE`
- `N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_POST_REVIEW_GATE`

## P0/P1/P2

P0/P1/P2 for current implementation state: `1 / 3 / 1`

P0:

- no structured query audit wrapper/helper exists

P1:

- 164 direct `psycopg.connect` occurrences across 90 files need wrapper adoption or explicit bypass classification
- no N3/N4/N5 application_name/run-id tagging convention exists
- denied-table script matches need non-runtime or approved-bypass classification

P2:

- optional `pg_stat_statements` aggregate supplement remains unavailable

## Forbidden Scope Proof

This gate did not:

- write database rows
- enable `pg_stat_statements`
- change PostgreSQL config
- execute migration
- modify N3/N4/N5 execute code
- consume/update outbox/inbox/checkpoint
- start worker
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade

## Decision

Contract decision: **CONTRACT_PASS**

Current implementation state: **BLOCKED_UNTIL_IMPLEMENTATION_GATE**

Next gate:

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION_GATE`

## Validation

- JSON parse: PASS
- `git diff --check`: PASS
- static inventory scan: PASS
- read-only only: PASS
- query audit helper scan: PASS, matches = 0
- N3/N4/N5 `application_name` tagging scan: PASS, matches = 0
