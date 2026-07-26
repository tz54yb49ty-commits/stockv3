# N6 B-track Product V3 Scope-write Source Validation 044

Status: implementation draft; migration and feature activation remain separate
gates.

## Purpose

Schema 044 hardens the already published 042 monitor and realtime upsert
functions. HTTP preflight remains defense in depth, but database authority no
longer depends on it: a direct restricted-role function call must pass the same
current approved-source check before any write can occur.

## Replaced functions

- `public.n6_btrack_monitor_upsert(text,text,text,text,text)`
- `public.n6_btrack_realtime_upsert(text,text,text,text)`

Both retain their 042 signatures, owners, `SECURITY DEFINER` property, fixed
`search_path = pg_catalog`, PUBLIC execute revocation, and the existing
`n6_btrack_web` execute grant. `CREATE OR REPLACE FUNCTION` preserves the
existing owner and ACL for an unchanged signature; 044 creates no role and
changes no grant.

## Fixed source mapping

| asset_kind | Current approved source |
|---|---|
| stock | `public.v_n6_stock_condition_display_basis` |
| index | `public.v_n6_index_condition_display_basis` |
| board | `public.v_n6_board_condition_display_basis` |

Each fixed branch embeds the view's `max(for_trade_date)`, the requested
`identity_key`, and the requested date directly in that branch's `INSERT ...
SELECT` (or `INSERT ... SELECT ... ON CONFLICT`) statement. The approved
source check and a successful DML therefore use the same SQL-statement
snapshot. There is no dynamic SQL and no fallback to condition basis/pool,
membership enrichment, N1-N5 facts, outbox, cache, or client authority.

Validation is ordered before DML:

1. active session/principal authority;
2. asset, identity format, and direction policy;
3. a scoped `INSERT ... SELECT` whose CTE requires both exact current
   `for_trade_date` and identity membership in the current approved view;
4. only when that DML returns zero rows, a read-only error classification.

A missing/current-date mismatch returns `current_for_trade_date_required`; an
identity absent from that current batch returns `source_not_found`. Both paths
perform zero DML because the corresponding `INSERT ... SELECT` has no source
row. Stock monitor direction remains buy-only; index and board allow buy and
sell.

## Rollback

Rollback uses `CREATE OR REPLACE FUNCTION` to restore the exact two definitions
published by Schema 042. It does not revoke grants, change owners, drop tables,
or delete business history. Existing monitor and realtime rows are preserved.

## Frozen non-goals

- No migration execution in this implementation gate.
- No feature flag activation, credential, role, service, plist, or 8786 change.
- No proposal, executor, order, trade, position, cash, scheduler, or poller work.
- No batch/selected-add UI and no legacy V2 write route.
