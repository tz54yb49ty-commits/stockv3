# N3_N4_N5_INTRADAY_ACCESS_OBSERVABILITY_DRY_RUN

Result: **BLOCKED_CURRENT_STATE**

Layer role: `runtime_control`

This dry-run checks current observability readiness for N3/N4/N5 intraday table-access attribution. It does not write DB rows, enable `pg_stat_statements`, change PostgreSQL config, run migration, modify N3/N4/N5 execute code, consume/update outbox/inbox/checkpoint, start workers, or enter delivery/push/voice/mobile/sim/position/PnL/real trade/proposal/order/trade.

## Read-Only DB Probe

Target:

- `ashare_v3 / ashare_v3_user / 127.0.0.1:5432`

Probe controls:

- `default_transaction_read_only=on`
- `statement_timeout=12000`
- `application_name=n3_n4_n5_observability_contract_probe`

Observed:

- connection: PASS
- `application_name` accepted: PASS
- tagged session visible in `pg_stat_activity`: PASS
- DB writes: 0
- worker started: false

## Current DB Observability

`pg_stat_statements`:

- available extension: yes, default version `1.10`
- installed extension rows: 0
- `to_regclass('public.pg_stat_statements')`: null
- `to_regclass('pg_catalog.pg_stat_statements')`: null
- status: BLOCKED for OBS-A until DB/config gate

`pg_stat_user_tables`:

- exists: true
- visible stats rows: 120
- status: available for future OBS-C pre/post counter probe

Current settings:

- `log_statement=none`
- `log_min_duration_statement=-1`
- `track_io_timing=off`
- `compute_query_id=auto`
- `shared_preload_libraries`: not readable by current role

Audit table candidates:

- `runtime_query_audit`: absent
- `common_query_audit`: absent
- `n3_n4_n5_query_audit`: absent
- `runtime_sql_audit`: absent
- `common_sql_audit`: absent

## Static Observability Scan

Scopes:

- `src/ashare_v3/market`
- `src/ashare_v3/trigger`
- `src/ashare_v3/action`
- `scripts`
- `tests`

Results:

- query audit helper matches: 0
- `application_name` tagging matches in N3/N4/N5 paths: 0
- `pg_stat_user_tables` / `pg_stat_statements` helper matches in N3/N4/N5 paths: 0

Decision:

- no existing structured observability helper detected

## Option Readiness

### OBS-A

Current readiness: **BLOCKED**

Reason:

- `pg_stat_statements` is available but not installed/enabled
- current role cannot inspect `shared_preload_libraries`
- enablement requires a separate DB/config gate

### OBS-B

Current readiness: **BLOCKED**

Reason:

- no structured query audit helper or audit sink detected
- N3/N4/N5 code has many direct `psycopg.connect` call sites that would need wrapper adoption or explicit bypass classification
- implementation requires a separate code gate

### OBS-C

Current readiness: **PARTIALLY_READY**

Reason:

- `application_name` works
- `pg_stat_activity` sees the tagged session
- `pg_stat_user_tables` is available

Limitation:

- cannot provide SQL text, exact query timestamp, or per-statement scanned rows

## Planned Items

1. `OBS-REM-001`: structured query audit implementation contract
   - next gate: `N3_N4_N5_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION_CONTRACT_GATE`
   - priority: P0

2. `OBS-REM-002`: fresh-run readonly probe contract
   - next gate: `N3_N4_N5_INTRADAY_ACCESS_FRESH_RUN_PROBE_CONTRACT_GATE`
   - priority: P1

3. `OBS-REM-003`: optional `pg_stat_statements` DB/config review
   - next gate: `POSTGRES_PG_STAT_STATEMENTS_CONFIG_REVIEW_GATE`
   - priority: P2

## Blockers

P0:

- `OBS-DRY-P0-001`: statement-level attribution remains unavailable because `pg_stat_statements` is not installed/enabled and no structured query audit helper exists.

P1:

- `OBS-DRY-P1-001`: N3/N4/N5 runtime DB paths do not show an existing `application_name` / run-id tagging convention.
- `OBS-DRY-P1-002`: no structured audit table/helper/sink exists for query timestamp/table/fingerprint evidence.

P2:

- `OBS-DRY-P2-001`: `shared_preload_libraries` cannot be examined by current DB role, so OBS-A preload readiness needs a DB/config review if pursued.

P0/P1/P2: `1 / 2 / 1`

## Decision

Dry-run decision: **BLOCKED_UNTIL_OBSERVABILITY_IMPLEMENTATION_OR_ACCEPTED_PROBE**

Recommended observability path:

`OBS-B structured query audit wrapper as primary, OBS-C fresh-run read-only probe as interim, OBS-A optional supplement`

Next recommended gate:

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION_CONTRACT_GATE`

## Forbidden Scope Proof

This dry-run did not:

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

## Validation

- JSON parse: PASS
- `git diff --check`: PASS
- read-only DB probe: PASS
- static scan: PASS
