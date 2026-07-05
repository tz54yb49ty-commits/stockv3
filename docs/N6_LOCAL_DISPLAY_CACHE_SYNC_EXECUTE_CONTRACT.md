# N6 Local Display Cache Sync Execute Contract

Gate: `N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_CONTRACT_IMPLEMENTATION_GATE`  
Layer role: `runtime_control`  
Result: `CONTRACT_PASS`  
Date: `2026-06-07`

This contract implements the missing N6 local display cache sync runner and execution contract. It does not execute sync, write cache rows, activate cache, consume outbox, start workers, or touch trading/user-action flows.

## Runner

Runner:

```text
scripts/run_n6_local_display_cache_sync_once.py
```

Implementation module:

```text
src/ashare_v3/user/local_display_cache_sync.py
```

Principal:

```text
system-only
```

The runner requires both:

```text
--execute
--user-confirmed
```

Missing either flag blocks before repository read or write.

## Execute Inputs

```text
cache_run_id=n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1
cache_version=n6_display_cache_v1
source_condition_run_id=condition_layer_20260604_source_20260604_v1
source_trade_date=20260604
mapping_strategy=cartesian_fanout_v1
```

## Allowed Command Shape

This command is for the next final gate review; it is not executed by this gate.

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

## Allowed Write Scope

The runner may write only:

- `n6_display_cache_run`
- `n6_stock_display_cache`
- `n6_index_display_cache`
- `n6_board_display_cache`
- `n6_index_membership_display_cache`
- `n6_board_membership_display_cache`

Allowed operations:

- insert `n6_display_cache_run` with `status=building` and `is_active=false`
- insert the five child cache tables
- after all validations pass, update only the target `n6_display_cache_run` row to `status=passed`, `is_active=true`

## Forbidden Scope

The runner must not write:

- N1/N2 source tables
- N3/N4/N5 facts
- N6 projection/card/notification tables
- outbox/inbox/checkpoint
- worker state
- proposal/order/trade
- position/PnL
- real trade

It must not read:

- `condition_basis`
- `condition_pool`
- `minute_target_scope`
- raw K
- direct live market
- N4/N5 raw facts bypass
- unreviewed outbox

## Expected Rows

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

## Idempotency

The runner blocks if:

- `cache_run_id` already exists
- target child rows already exist for the `cache_run_id/cache_version`
- an active cache already exists for the same source run/version
- any active cache exists for this first-run cache version, because pointer replacement must be handled by a separate pointer-switch gate

## Activation Policy

Activation is allowed only after all expected row counts and validation checks pass:

```text
duplicate_fanout_key=0
duplicate_row_hash=0
missing_required=0
invalid_board_type=0
invalid_direction=0
null_identity_key=0
```

Partial activation is forbidden.

## Rollback

Rollback SQL:

```text
sql/N6_local_display_cache_sync_20260604_rollback.sql
```

Rollback is scoped to the target `cache_run_id/cache_version`; it does not drop schema tables, touch source tables, touch N3/N4/N5 facts, touch N6 projection/card, or touch outbox/inbox/checkpoint.

## Decision

`CONTRACT_PASS`

Next gate:

```text
N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_FINAL_GATE_REVIEW
```
