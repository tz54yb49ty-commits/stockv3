# N6 Local Display Cache Sync Execute Final Gate Review

Gate: `N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_FINAL_GATE_REVIEW`  
Layer role: `runtime_control`  
Result: `PASS`  
Date: `2026-06-07`

This gate was read-only. No sync was executed, no database rows were written, no cache was activated, no outbox was consumed or updated, and no worker or trading-related flow was started.

## Final Gate Findings

The execute runner, contract, preflight artifact, rollback SQL, and live DB baseline are aligned. The sync may enter the user confirmation point for the exact command listed below.

Fresh DB proof:

```text
database=ashare_v3
user=ashare_v3_user
host=127.0.0.1
port=5432
db_time=2026-06-07T13:59:15.906163+08:00
```

## Source Proof

Latest active N2 run remains:

```text
run_id=condition_layer_20260604_source_20260604_v1
status=passed_active
created_at=2026-06-04T21:18:57.194566+08:00
```

Source row counts still match the dry-run refresh:

| Source | Rows |
|---|---:|
| `stock_condition_display_basis` | 1,952 |
| `index_condition_display_basis` | 9 |
| `board_condition_display_basis` | 428 |
| `index_membership_fact` | 12,841 |
| `board_membership_fact` | 56,960 |

Fanout preview still matches:

```text
stock display preview = 8370
index display preview = 40
board display preview = 1824
```

## Target Baseline

All six cache tables exist and remain empty:

| Table | Row Count |
|---|---:|
| `n6_display_cache_run` | 0 |
| `n6_stock_display_cache` | 0 |
| `n6_index_display_cache` | 0 |
| `n6_board_display_cache` | 0 |
| `n6_index_membership_display_cache` | 0 |
| `n6_board_membership_display_cache` | 0 |

Idempotency baseline:

```text
cache_run_id rows = 0
active cache same version rows = 0
active cache same source/version rows = 0
cache_run_id scoped child rows = 0
```

There is currently no active cache, so no old active pointer needs restore for this first sync.

## Contract / Preflight Proof

Contract and preflight are consistent:

```text
contract result = CONTRACT_PASS
preflight result = PREFLIGHT_PASS
cache_run_id = n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1
cache_version = n6_display_cache_v1
source_condition_run_id = condition_layer_20260604_source_20260604_v1
source_trade_date = 20260604
mapping_strategy = cartesian_fanout_v1
```

Expected execute rows:

| Target | Rows |
|---|---:|
| `n6_display_cache_run` | 1 |
| `n6_stock_display_cache` | 8,370 |
| `n6_index_display_cache` | 40 |
| `n6_board_display_cache` | 1,824 |
| `n6_index_membership_display_cache` | 12,841 |
| `n6_board_membership_display_cache` | 56,960 |
| Total excluding run | 80,035 |
| Total including run | 80,036 |

Dry-run validation remains clean:

```text
duplicate fanout key = 0
duplicate row_hash = 0
missing required = 0
invalid board_type = 0
invalid direction = 0
null identity_key = 0
```

Runner guard proof:

```text
missing --execute blocks before DB read/write = true
missing --user-confirmed blocks before DB write = true
missing --execute no-op result = BLOCKED / missing_execute_flag
database_written = false
outbox_consumed_or_updated = false
worker_started = false
```

## Allowed Execute Command

Only the following command is allowed after explicit user confirmation:

```bash
PYTHONPATH=src:scripts python3 scripts/run_n6_local_display_cache_sync_once.py \
  --cache-run-id n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1 \
  --cache-version n6_display_cache_v1 \
  --source-condition-run-id condition_layer_20260604_source_20260604_v1 \
  --source-trade-date 20260604 \
  --mapping-strategy cartesian_fanout_v1 \
  --contract-path docs/N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_CONTRACT.json \
  --preflight-path docs/N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_PREFLIGHT.json \
  --rollback-sql-path sql/N6_local_display_cache_sync_20260604_rollback.sql \
  --json-report-path docs/N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_REPORT.json \
  --markdown-report-path docs/N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_REPORT.md \
  --execute \
  --user-confirmed
```

Allowed write scope for that command is limited to:

- `n6_display_cache_run`
- `n6_stock_display_cache`
- `n6_index_display_cache`
- `n6_board_display_cache`
- `n6_index_membership_display_cache`
- `n6_board_membership_display_cache`

## Activation Policy

Execute may activate this cache only after all inserts, row counts, and validations pass. If any expected row count mismatches, or any duplicate/required-field validation fails, the runner must not set `is_active=true`.

Current baseline has no active cache. Future replacement of an old active cache must use a separate pointer-switch gate or block under this first-run runner policy.

## Rollback Proof

Rollback SQL:

```text
sql/N6_local_display_cache_sync_20260604_rollback.sql
```

Static proof:

```text
RAISE EXCEPTION before first UPDATE = true
RAISE EXCEPTION before first DELETE = true
delete scope only cache_run_id/cache_version = true
deactivate scope only cache_run_id/cache_version = true
no DROP TABLE / CASCADE / TRUNCATE = true
does not touch N1/N2 source tables = true
does not touch N3/N4/N5 facts = true
does not touch N6 projection/card tables = true
does not touch outbox/inbox/checkpoint = true
guards outbox/inbox/checkpoint refs = true
guards N6 projection/card/notification refs = true
```

The rollback only deactivates and deletes rows for:

```text
cache_run_id=n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1
cache_version=n6_display_cache_v1
```

## Forbidden Source Proof

Runner source scan passed. It does not read:

- `condition_basis`
- `condition_pool`
- `minute_target_scope`
- raw K
- direct live market
- N4/N5 raw facts bypass
- unreviewed outbox

Runner source scan also found no writes to N1/N2 source tables, N3/N4/N5 facts, N6 projection/card tables, outbox/inbox/checkpoint, proposal/order/trade, position/PnL, or real trade surfaces.

## Forbidden Scope Proof

This gate did not:

- write DB rows
- execute sync
- activate cache
- consume or update outbox
- start worker
- modify N3/N4/N5/N6 action flow
- generate proposal/order/trade
- update position/PnL
- submit real trade

## Validation

```text
JSON parse: PASS
source count assertion: PASS
target baseline assertion: PASS
contract/preflight assertion: PASS
rollback static check: PASS
duplicate/idempotency assertion: PASS
forbidden source scan: PASS
runner missing-execute guard: PASS
targeted unittest: PASS
compileall: PASS
git diff --check: PASS
```

## Decision

`PASS`

允许进入 `N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE` 用户确认点。Execute 后只允许进入 `N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_POST_REVIEW_REGISTRATION_GATE`，不得自动进入 N3/N4/N5/N6 action flow、outbox、worker、proposal/order/trade、position/PnL 或 real trade。
