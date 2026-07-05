# N3_N4_N5_INTRADAY_ACCESS_OBSERVABILITY_CONTRACT_GATE

Result: **CONTRACT_PASS**

Layer role: `runtime_control`

This contract defines the observability path needed to unblock N3/N4/N5 intraday table-access localization. It does not authorize DB writes, `pg_stat_statements` enablement, PostgreSQL config changes, migrations, N3/N4/N5 execute-code edits, outbox/inbox/checkpoint consumption, workers, delivery/push/voice/mobile, sim/position/PnL/real trade, or proposal/order/trade generation.

## Background

Input artifacts:

- `docs/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_REMEDIATION_CONTRACT.md`
- `docs/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_REMEDIATION_CONTRACT.json`
- `docs/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_REMEDIATION_DRY_RUN.md`
- `docs/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_REMEDIATION_DRY_RUN.json`

Current localization remediation state:

- `pg_stat_statements`: absent / not installed
- static scan direct matches for denied display/membership tables: 0
- requested local cache tables: absent
- local hotspots: `common_trigger_match`, `common_trigger_state`, `stock_trigger_context_snapshot`, `common_action_event`
- previous dry-run P0/P1/P2: `1 / 2 / 1`

The remaining P0 is statement-level attribution.

## Denied Direct Reads

N3/N4/N5 intraday worker/execute paths must not directly read:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

Allowed exception:

- N4 one-time context refresh may read approved N2 basis/pool/scope or condition context enrichment sources.
- The exception must be tagged as `one_time_context_refresh`, not as an intraday worker path.

## Observability Options

### OBS-A: `pg_stat_statements` + `application_name`

Plan:

- enable `pg_stat_statements` only in a separate DB/config gate
- require runner connection tagging with `application_name=layer/run_id/stage/gate_id`
- take pre/post snapshots for scoped observed runs

Can prove:

- normalized SQL text
- calls, rows, timing, and some IO counters
- denied table references when query text is retained
- aggregate hotspot query shapes

Cannot prove alone:

- exact per-call timestamp
- `application_name` attribution inside `pg_stat_statements`
- historical reads before enablement
- low-noise attribution when unrelated traffic runs concurrently

Status: useful optional supplement, but not the recommended primary path.

### OBS-B: Structured Query Audit Wrapper

Plan:

- add an application-side audited DB helper in a later implementation gate
- record layer, run id, stage, gate id, `application_name`, statement fingerprint, referenced tables, start/end timestamps, duration, rowcount, read-only flag, worker flag, and outbox/checkpoint side-effect flags
- implement a denylist guard before executing high-frequency N3/N4/N5 statements
- begin with docs JSON / stdout artifact sink; DB sink is not authorized in this gate

Can prove:

- per-query timestamp and duration
- run-id attribution
- referenced table list
- direct denied table hits
- rowcount where cursor metadata allows it
- explicit no-worker/no-outbox side-effect flags

Cannot prove:

- queries outside the wrapper
- internal DB reads caused by triggers/functions unless separately instrumented
- physical scanned rows without EXPLAIN or pg_stat support
- historical runs before adoption

Status: **recommended primary path**.

### OBS-C: Fresh-Run Read-Only Probe

Plan:

- for a later manually approved dry-run only, set `application_name`
- capture `pg_stat_user_tables` counters before and after a scoped N3/N4/N5 read-only probe
- compare deltas for the five denied display/membership tables

Can prove:

- tagged sessions are visible through `pg_stat_activity`
- `pg_stat_user_tables` counter deltas for a fresh observed run
- aggregate no-touch proof for denied tables if there is no concurrent noise

Cannot prove:

- SQL text
- exact query timestamp
- which statement caused a table delta
- per-statement scanned rows

Status: interim proof only, not sufficient as durable statement-level attribution.

## Recommended Path

Recommended path: **OBS-B primary + OBS-C interim + OBS-A optional supplement**.

Rationale:

- OBS-B is the only option that directly satisfies per-query timestamp/table/run-id attribution without depending on PostgreSQL extension state.
- OBS-C can quickly provide a no-write interim proof because `application_name` and `pg_stat_user_tables` are available now.
- OBS-A remains useful for normalized SQL and hotspot metrics, but it requires a DB/config gate and does not carry per-call timestamp or application-name attribution by itself.

Primary next gate:

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION_CONTRACT_GATE`

Interim optional gate:

`N3_N4_N5_INTRADAY_ACCESS_FRESH_RUN_PROBE_CONTRACT_GATE`

Optional DB/config gate:

`POSTGRES_PG_STAT_STATEMENTS_CONFIG_REVIEW_GATE`

## Structured Audit Minimum Contract

Required fields:

- `audit_event_id`
- `audit_run_id`
- `layer_role`
- `source_run_id`
- `stage_id`
- `gate_id`
- `application_name`
- `statement_fingerprint`
- `statement_kind`
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
- `audit_sink`

Allowed initial sink:

- docs JSON artifact
- stdout captured by gate runner

DB sink status:

- not authorized in this gate

Denylist rule:

- if `referenced_tables` intersects the five denied display/membership tables in N3/N4/N5 intraday worker/execute paths, the later implementation must BLOCK before DB execution.

Approved bypass rule:

- N4 one-time context refresh may read approved N2 basis/pool/scope or condition context enrichment sources, but it must be explicitly tagged and audited as one-time context refresh.

## Acceptance Criteria

The observability blocker is not resolved until all required criteria pass:

1. Every observed N3/N4/N5 probe or runner has layer/run-id/stage/gate attribution.
2. Direct references to the five denied display/membership tables are detectable.
3. Observed N3/N4/N5 intraday path shows zero direct reads of those denied tables.
4. Evidence records timestamp, referenced table, statement count, and rowcount; scan rows may come from pg_stat/EXPLAIN or an accepted substitute.
5. `worker_started=false` unless a later worker gate explicitly authorizes bounded worker smoke.
6. No N3/N4/N5 fact writes, outbox/inbox/checkpoint mutation, delivery, sim, position, real trade, proposal, order, or trade.

## P0/P1/P2 Policy

P0:

- no statement-level or accepted substitute attribution exists
- any N3/N4/N5 intraday worker/execute path directly reads denied display/membership tables

P1:

- missing `application_name` / run-id tagging in one or more N3/N4/N5 runner paths
- wrapper exists but does not cover all intraday query paths
- scan-row evidence is unavailable and no accepted substitute is documented

P2:

- optional pg_stat aggregate supplement remains absent after OBS-B passes
- static guard exists but non-runtime allowlist classification is incomplete

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

Current observability state: **BLOCKED_UNTIL_FOLLOW_UP_GATE**

Next recommended gate:

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION_CONTRACT_GATE`

## Validation

- JSON parse: PASS
- `git diff --check`: PASS
- static source scan: PASS, query audit helper matches = 0, N3/N4/N5 `application_name` tagging matches = 0
- read-only DB probe: PASS, `application_name` visible in `pg_stat_activity`, `pg_stat_user_tables` exists, `pg_stat_statements` not installed, DB writes = 0, worker started = false
