# N3_N4_N5_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION_DRY_RUN

Result: **BLOCKED_CURRENT_STATE**

Layer role: `runtime_control`

This dry-run inventories current direct DB access paths and implementation gaps for the structured query audit wrapper. It does not change code, write database rows, enable `pg_stat_statements`, change PostgreSQL config, run migration, consume/update outbox/inbox/checkpoint, start workers, or enter delivery/push/voice/mobile/sim/position/PnL/real trade/proposal/order/trade.

## Direct `psycopg.connect` Inventory

| scope | direct occurrences | unique files |
|---|---:|---:|
| `src/ashare_v3/market` | 70 | 32 |
| `src/ashare_v3/trigger` | 43 | 14 |
| `src/ashare_v3/action` | 8 | 7 |
| `scripts` | 43 | 37 |
| total | 164 | 90 |

Top files:

- `src/ashare_v3/trigger/context_execute.py`: 9
- `src/ashare_v3/trigger/c3_replay_audit_execute.py`: 6
- `src/ashare_v3/market/previous_day_preload_execute.py`: 6
- `src/ashare_v3/market/action_confirmation_metric_materialization_execute.py`: 6
- `src/ashare_v3/market/today_minute_execute.py`: 5
- `src/ashare_v3/market/realtime_snapshot_execute.py`: 5
- `src/ashare_v3/trigger/run_once_execute.py`: 4
- `src/ashare_v3/trigger/local_trigger_dry_run.py`: 4
- `scripts/plan_n4_trigger_rule_v4_full_lineage_dry_run.py`: 4

Decision:

- current coverage is BLOCKED until these sites are wrapped or explicitly classified.

## Missing Wrapper / Helper Status

- query audit helper matches: 0
- N3/N4/N5 `application_name` tagging matches: 0
- artifact sink detected: false
- denylist guard detected: false
- static coverage test detected: false

Status: **missing**

## Denied Table Static Scan

N3/N4/N5 runtime source paths:

- denied table direct matches: 0

Scripts:

- denied table matches: 14
- classification required: true
- observed context: N1/N2/condition scripts and ingestion/archive membership references, not accepted as N3/N4/N5 intraday proof until classified

## Implementation File Plan

Create in later implementation gate:

- `src/ashare_v3/observability/__init__.py`
- `src/ashare_v3/observability/query_audit.py`
- `tests/test_structured_query_audit.py`
- `tests/test_structured_query_audit_static_coverage.py`

Modify later only after implementation authorization:

- N3 market DB access paths
- N4 trigger DB access paths
- N5 action DB access paths
- N3/N4/N5 scripts `run_*` / `plan_*` entrypoints

Bypass classification required for:

- N1/N2 ingestion and condition scripts
- schema migration review/execute helpers
- N4 one-time context refresh

## Validation Command Plan

```bash
python3 -m unittest tests/test_structured_query_audit.py
python3 -m unittest tests/test_structured_query_audit_static_coverage.py
python3 -m compileall src/ashare_v3/observability src/ashare_v3/market src/ashare_v3/trigger src/ashare_v3/action scripts
python3 -m json.tool docs/N3_N4_N5_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION_REPORT.json >/dev/null
git diff --check
```

## Blockers

P0:

- `SQA-DRY-P0-001`: no structured query audit wrapper/helper exists, so statement-level attribution remains unavailable.

P1:

- `SQA-DRY-P1-001`: 164 direct `psycopg.connect` occurrences across 90 files need wrapper adoption or explicit bypass classification.
- `SQA-DRY-P1-002`: no N3/N4/N5 application_name/run-id tagging convention exists.
- `SQA-DRY-P1-003`: denied-table script matches require explicit non-runtime or approved-bypass classification.

P2:

- `SQA-DRY-P2-001`: optional `pg_stat_statements` aggregate supplement remains unavailable.

P0/P1/P2: `1 / 3 / 1`

## Decision

Dry-run decision: **BLOCKED_UNTIL_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION**

Next gate:

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_IMPLEMENTATION_GATE`

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
- static inventory scan: PASS
- query audit helper scan: PASS, matches = 0
- N3/N4/N5 `application_name` tagging scan: PASS, matches = 0
