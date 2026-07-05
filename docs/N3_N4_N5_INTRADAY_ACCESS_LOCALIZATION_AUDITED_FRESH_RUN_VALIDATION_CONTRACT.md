# N3/N4/N5 Intraday Access Localization Audited Fresh-Run Validation Contract

Gate: `N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_CONTRACT_GATE`

Result: `CONTRACT_PASS`

Layer role: `runtime_control`

Generated on: `2026-06-07`

## Objective

Define the read-only audited fresh-run validation contract for proving that N3/N4/N5 intraday paths do not directly read external N2 `display_basis` or `membership_fact` tables.

This gate generates only contract and dry-run planning artifacts. It does not execute N3/N4/N5 runners, write database rows, run migrations, consume outbox/inbox/checkpoint rows, start workers, or enter delivery, sim, position, PnL, real trade, proposal, order, or trade flows.

## Current State

Structured query audit adoption is closed out:

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_ADOPTION_CLOSEOUT_GATE = CLOSEOUT_PASS`

Current static coverage:

| Scope | Direct `psycopg.connect` sites |
|---|---:|
| `src/ashare_v3/market` | 0 |
| `src/ashare_v3/trigger` | 0 |
| `src/ashare_v3/action` | 0 |
| `scripts` | 33 |

The remaining `33` script sites are N1/N2/ingestion only and are outside this N3/N4/N5 runtime validation scope.

`docs/query_audit` is currently absent, so no fresh-run audit artifacts exist yet. That is expected for this contract gate.

## Validation Objective

The future validation gate must prove:

- N3/N4/N5 read-only fresh-run probe paths produce statement-level audit artifacts.
- No audit entry references the denied external display/membership tables.
- No probe attempts database writes.
- No probe starts workers or mutates outbox/inbox/checkpoint state.
- Pre/post snapshots show no forbidden mutation.

Denied tables:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

## Fresh-Run Contract

Mode: `read_only_audited_probe`

Artifact directory:

```text
docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION
```

Required environment:

```bash
PYTHONPATH=src:scripts
ASHARE_QUERY_AUDIT_DIR=docs/query_audit/N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION
ASHARE_QUERY_AUDIT_SOURCE_RUN_ID=runtime_control_intraday_access_localization_validation_20260607
```

Allowed command shapes:

- read-only plan
- dry-run
- preflight
- audit probe

Forbidden flags:

- `--execute`
- `--user-confirmed`
- `--consume`
- `--worker`
- `--delivery`
- `--trade`

Forbidden effects:

- database writes
- outbox/inbox/checkpoint updates
- worker startup
- external market data pull unless a later `N3_market_data` gate explicitly authorizes it
- N4/N5/N6 fact mutation

## Minimum Probe Matrix

| Layer | Required evidence | Allowed path roles |
|---|---|---|
| N3 market data | At least one audited read-only N3 market planning/preflight artifact with `layer_role=N3_market_data` | `n3_readonly_plan` |
| N4 trigger | At least one audited read-only N4 trigger dry-run/preflight artifact with `layer_role=N4_trigger` | `n4_readonly_plan` |
| N5 action | At least one audited read-only N5 action dry-run/preflight artifact with `layer_role=N5_action` | `n5_readonly_plan` |

## Artifact Acceptance Criteria

- Audit artifact directory exists.
- N3/N4/N5 read-only probe artifacts exist and parse as JSON.
- Every audit entry includes layer, source run, stage, gate, path role, application name, SQL fingerprint, referenced tables, timestamps, duration, rowcount, readonly flag, and side-effect flags.
- All probe entries have `readonly_transaction=true`.
- No probe entry has `db_write_attempted=true`.
- No probe entry has `worker_started=true`, `outbox_consumed=true`, or `checkpoint_updated=true`.
- No probe entry references any denied table.
- `blocked_entries=0`.
- `denied_table_hit_entries=0`.

## Pre/Post Snapshot Requirement

The next validation gate must capture pre/post read-only snapshots for:

- `common_event_outbox` status counts
- scoped `common_event_inbox` counts
- scoped `common_event_consumer_checkpoint` counts
- scoped `common_trigger_match` counts
- scoped `common_trigger_state` counts
- scoped `common_action_event` counts
- N6 projection/card/notification scoped counts when present

Acceptance: pre/post snapshots must be equal for all forbidden mutation scopes.

## Future P0 Guards

Future validation must block on:

- missing required audit artifact
- denied table reference
- database write attempt
- side-effect flag or pre/post snapshot mismatch
- unauthorized execute/worker/consume/delivery/trade semantics

## P0/P1/P2

`P0/P1/P2 = 0/2/0`

P1 items:

- No fresh-run audit artifacts exist yet; this contract only defines the validation gate.
- 33 N1/N2/ingestion scripts remain outside N3/N4/N5 runtime validation scope.

## Forbidden Scope Proof

This gate did not perform or authorize:

- DB writes or migrations
- `pg_stat_statements` enablement
- PostgreSQL config changes
- N3/N4/N5 runner execution
- worker startup
- outbox/inbox/checkpoint consumption or mutation
- delivery, push, voice, or mobile
- sim, position, PnL, or real trade
- proposal, order, or trade

## Next Gate Recommendation

`N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_PREFLIGHT_GATE`
