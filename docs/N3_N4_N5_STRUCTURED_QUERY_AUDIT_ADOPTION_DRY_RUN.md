# N3_N4_N5_STRUCTURED_QUERY_AUDIT_ADOPTION_DRY_RUN

Result: **CONTRACT_DRY_RUN_PASS_WITH_P1_REMAINDERS**

Layer role: `runtime_control`

This dry-run creates a classification baseline for adopting the structured query audit wrapper. It does not modify code, integrate runners, write database rows, enable `pg_stat_statements`, change PostgreSQL config, run migrations, consume outbox/inbox/checkpoint, start workers, or enter delivery/sim/trade scopes.

## Static Inventory

| scope | direct sites |
|---|---:|
| `src/ashare_v3/market` | 70 |
| `src/ashare_v3/trigger` | 43 |
| `src/ashare_v3/action` | 8 |
| `scripts` | 43 |
| total | 164 |

Unique files: 90

## Classification Baseline

| classification | site count |
|---|---:|
| `must_wrap` | 12 |
| `explicit_bypass_one_time_context_refresh` | 9 |
| `explicit_bypass_readonly_plan` | 39 |
| `out_of_scope_n1_n2_or_migration` | 40 |
| `blocked_until_refactored` | 64 |
| total | 164 |

Unclassified after draft: 0

`blocked_until_refactored` remains an explicit P1 classification, not implementation completion.

## Phase 1 Dry-Run

Phase: `phase_1_n4_trigger_high_risk`

- target files: 9
- target direct sites: 24
- unclassified: 0
- `must_wrap`: 12
- `explicit_bypass_one_time_context_refresh`: 9
- `explicit_bypass_readonly_plan`: 3

Recommended action:

Proceed to a phase 1 implementation gate that only adopts wrapper/classification for the listed N4 high-risk files.

## Blockers

P0/P1/P2: `0 / 2 / 1`

P1:

- `ADOPT-P1-001`: 164 global direct connect sites remain unwrapped.
- `ADOPT-P1-002`: 64 sites are explicitly `blocked_until_refactored`.

P2:

- `ADOPT-P2-001`: optional `pg_stat_statements` supplement remains unavailable.

## Forbidden Scope Proof

This dry-run did not:

- modify code
- write database rows
- enable `pg_stat_statements`
- change PostgreSQL config
- execute migration
- integrate real N3/N4/N5 runner paths
- consume/update outbox/inbox/checkpoint
- start worker
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade

## Next Gate

Recommended next gate:

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE1_N4_ADOPTION_IMPLEMENTATION_GATE`

## Validation

- JSON parse: PASS
- static inventory command: PASS, current raw inventory remains 164 sites / 164 unclassified before applying the adoption baseline
- existing wrapper tests: PASS, 7 + 4 tests
- `git diff --check`: PASS
