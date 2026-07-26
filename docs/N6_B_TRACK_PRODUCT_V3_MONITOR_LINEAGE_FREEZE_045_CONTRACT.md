# N6 B-track Product V3 Monitor Lineage Freeze 045

Status: exact seven-file implementation draft; database execution, feature
activation, release and runtime operations remain separate gates.

## Purpose

Schema 045 closes the monitor lineage writer/reader gap. A new monitor can be
created only when one current approved display-basis batch is complete and
unique, and the inserted row freezes that batch's `source_trade_date`,
`for_trade_date`, and `run_id`. Signals, messages, and SSE use the same exact
lineage contract for the monitor branch.

## Writer contract

045 replaces only
`public.n6_btrack_monitor_upsert(text,text,text,text,text)`. Its signature,
owner, volatility, `SECURITY DEFINER`, `search_path = pg_catalog`, PUBLIC
revocation and `n6_btrack_web` ACL remain unchanged. The realtime upsert
function is not replaced.

Each stock/index/board branch uses one atomic `INSERT ... SELECT` statement and
its fixed approved view:

| asset kind | approved source |
|---|---|
| stock | `public.v_n6_stock_condition_display_basis` |
| index | `public.v_n6_index_condition_display_basis` |
| board | `public.v_n6_board_condition_display_basis` |

The statement selects the maximum current `for_trade_date`, then requires every
row in that date to have non-null `source_trade_date`, `for_trade_date`, and
`run_id`, with exactly one distinct three-field batch. The requested identity
must exist in that exact batch. Missing values, a missing identity, an old
requested date, or multiple batch triples produce zero DML.

The successful insert writes `source_run_id`, `valid_source_trade_date`,
`valid_for_trade_date`, and `valid_source_run_id`. `source_snapshot_json`
freezes `identity_key` and the complete three-field batch.

Stock remains buy-only. Index and board allow buy and sell. Principal, user,
and requested current trade-date isolation are unchanged.

## Reader contract

The monitor UI and the shared effective-monitor CTE used by signals, message
dashboard, signal detail, SSE, and cold scope metadata accept a monitor row only
when all four formal lineage columns are non-empty, both run-id columns equal
the current `run_id`, and the frozen three-field batch exactly equals the one
complete and unique current batch from the matching approved view. The identity
must also still exist in that exact batch. The UI does not recover formal
lineage columns from `source_snapshot_json`.

The monitor-list read proves exact identity membership once in its asset query.
Its display-row lateral join is bound to the same identity,
`source_trade_date`, `for_trade_date`, and `run_id`, and returns at most one
display row. An incomplete or non-unique current batch therefore cannot attach
display data, duplicate a monitor row, or make it effective.

This rule applies only to `user_monitor_stock/index/board`. Realtime scope,
default realtime seed, and virtual-position scope retain their existing range
and are not required to carry monitor lineage.

No per-message enrichment is added. No N2-N5 raw table, outbox, membership,
projection/quote scheduler, or external source is read. Cold scope metadata
keeps the existing single-query and cache contract and its 2000 ms budget.

## Rollback and activation

Rollback uses `CREATE OR REPLACE FUNCTION` to restore byte-for-byte the monitor
function definition published by Schema 044. It does not delete or rewrite any
monitor history and does not replace the realtime function. Runtime rollout
must keep the scope-write feature flag disabled after rollback.

This gate does not execute 045, stage or commit files, modify runtime plist,
release artifacts, schedulers, N1-N5, projection data, or real trading state.
