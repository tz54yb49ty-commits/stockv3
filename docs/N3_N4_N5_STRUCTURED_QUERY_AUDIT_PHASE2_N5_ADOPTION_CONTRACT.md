# N3/N4/N5 Structured Query Audit Phase 2 N5 Adoption Contract

Gate: `N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE2_N5_ADOPTION_CONTRACT_GATE`

Date: 2026-06-07

Layer role: `runtime_control`

Result: `CONTRACT_PASS`

## Scope

This contract defines Phase 2 adoption of the structured query audit wrapper for selected N5 action paths.

This gate is docs/classification only. It does not modify code, write database rows, execute N5 runners, integrate real execute/worker paths, consume outbox/inbox/checkpoint rows, start workers, enter N6, enable `pg_stat_statements`, change PostgreSQL config, or execute migrations.

## Current State

- Phase 1 N4 adoption: `POST_REVIEW_PASS`
- Phase 1 direct sites: 0
- global remaining direct sites: 140

Remaining by scope:

| scope | direct sites |
|---|---:|
| `src/ashare_v3/market` | 70 |
| `src/ashare_v3/trigger` | 24 |
| `src/ashare_v3/action` | 8 |
| `scripts` | 38 |

## Phase 2 Scope

Selected N5 action files:

| file | direct sites | classification |
|---|---:|---|
| `src/ashare_v3/action/execute.py` | 1 | `must_wrap` |
| `src/ashare_v3/action/metadata_repair.py` | 1 | `explicit_bypass_metadata_repair` |
| `src/ashare_v3/action/execute_preflight.py` | 1 | `explicit_bypass_readonly_plan` |
| `src/ashare_v3/action/preflight.py` | 1 | `explicit_bypass_readonly_plan` |
| `src/ashare_v3/action/consumer_dry_run.py` | 1 | `explicit_bypass_readonly_plan` |
| `src/ashare_v3/action/run_once_dry_run.py` | 1 | `explicit_bypass_readonly_plan` |

Out of scope for Phase 2 runtime adoption:

| file | direct sites | classification |
|---|---:|---|
| `src/ashare_v3/action/schema_migration_execute.py` | 2 | `out_of_scope_migration_or_schema_review` |

Scripts are classified but not integrated in this gate. Current selected N5 script entrypoints have no direct `psycopg.connect` site; they delegate into N5 action modules.

## Classification Baseline

| classification | site count |
|---|---:|
| `must_wrap` | 1 |
| `explicit_bypass_metadata_repair` | 1 |
| `explicit_bypass_readonly_plan` | 4 |
| `out_of_scope_migration_or_schema_review` | 2 |
| `blocked_until_refactored` | 0 |

Phase 2 selected scope:

- unclassified: 0
- `blocked_until_refactored`: 0

Taxonomy note:

Current `query_audit.VALID_CONNECTION_SITE_CLASSIFICATIONS` does not yet include `explicit_bypass_metadata_repair` or `out_of_scope_migration_or_schema_review`. The Phase 2 implementation gate must either add these states to the static coverage helper or map them to existing wrapper classifications with explicit report evidence.

## N5 Denylist / Guard Policy

N5 intraday/action execute paths must block direct access to:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

N5 also remains forbidden from:

- raw K
- N1 raw facts
- direct live market
- N4 raw facts bypass
- unreviewed outbox direct consumption
- N6 projection/card mutation

Allowed source policy:

N5 may consume reviewed N4 `TriggerMatched` events/outbox and deterministic approved N3 metric artifacts according to contract. It must not query external N2 display/membership tables or reconstruct upstream semantics from raw facts.

## Metadata Repair Policy

If metadata repair enters Phase 2 adoption, it must remain scoped to metadata-only repair.

Allowed metadata keys:

- `blocked_reason`
- `action_confirmation_metric_run_refs`
- `metric_union_policy_version`
- `metric_union_source_runs`
- `metric_coverage_status`
- `metric_missing_resolved`
- `repair_trace`

Forbidden mutations:

- action status/state
- confirmation status
- action mark
- event id
- action run id
- source trigger event id
- outbox status
- delivery status
- N4 payload
- N3 metric rows
- N6 projection/card

Required guards:

- BLOCK if N5 outbox delivered/delivering
- BLOCK if downstream inbox/checkpoint consumed
- BLOCK if N6 projection/card already propagated from this repair
- BLOCK if notification/delivery/push/voice/mobile refs exist
- BLOCK if sim/position/PnL/real trade refs exist

Audit policy:

Metadata repair writes must be artifact-first audited and must record `db_write_attempted=true` while preserving scoped metadata-only semantics.

## Acceptance Criteria

- Phase 2 N5 selected scope unclassified = 0
- Phase 2 selected files have no `blocked_until_refactored`
- denied table guard tests still pass
- artifact sink only
- no real N5 runner execution
- no DB writes in this gate
- global remaining unwrapped sites documented as P1
- JSON parse passes
- static inventory passes
- existing tests pass
- `git diff --check` passes

## Validation

- JSON parse: PASS
- static inventory: PASS, Phase 2 selected action direct sites = 6, action total = 8, global direct sites = 140
- existing structured query audit tests: PASS, 7 + 4 + 2 tests
- `git diff --check`: PASS

## P0/P1/P2

P0/P1/P2: `0 / 2 / 1`

P1:

- Phase 2 selected N5 sites are classified but not yet adopted into code.
- Global remaining direct sites outside selected Phase 2 scope remain documented for later gates.

P2:

- Phase 2 taxonomy introduces metadata-repair and migration/schema classifications not yet present in `VALID_CONNECTION_SITE_CLASSIFICATIONS`.

## Forbidden Scope Proof

This gate does not:

- modify code
- write database rows
- execute N5 runners
- integrate real N5 execute/worker paths
- consume/update outbox/inbox/checkpoint
- start workers
- enter N6
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade
- enable `pg_stat_statements`
- change PostgreSQL config
- execute migration

## Next Gate

Recommended next gate:

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE2_N5_ADOPTION_IMPLEMENTATION_GATE`
