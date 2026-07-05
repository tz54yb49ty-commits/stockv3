# N3/N4/N5 Intraday Access Localization Hotspot Remediation Planning

Result: `PLANNING_PASS`  
Layer role: `runtime_control`  
Generated at: `2026-06-07T05:44:14.851731+00:00`

## Objective

Plan remediation for local N3/N4/N5 runtime hotspot tables after external N2 display/membership access localization has been closed out.

## Input Proof

- Access localization closeout: `CLOSEOUT_PASS`
- Scoped audit artifacts / entries: `7` / `33`
- Denied external display/membership table hits: `0`
- DB catalog probe transaction_read_only: `on`

## Hotspot Catalog Stats

| Table | Estimated rows | Seq scans | Seq tuples read | Index scans | Index tuples fetched | Total bytes |
|---|---:|---:|---:|---:|---:|---:|
| `common_trigger_match` | 109634 | 13222 | 1340786218 | 38146 | 1792950 | 401268736 |
| `common_trigger_state` | 76201 | 255 | 16806678 | 117959 | 1421876 | 323313664 |
| `stock_trigger_context_snapshot` | 42894 | 312 | 10720255 | 177 | 605290 | 157917184 |
| `common_action_event` | 16594 | 405 | 5946399 | 17261 | 1654922 | 152576000 |

## Priority Assessment

- `common_trigger_match`: `P1-highest` - Largest historical seq_tup_read and broad trigger/report/downstream reference surface.
- `common_trigger_state`: `P1-medium` - State table has high idx usage but still meaningful sequential tuple reads; audit predicates before changing indexes.
- `stock_trigger_context_snapshot`: `P1-high` - Context table has material seq_tup_read with low idx_scan relative to trigger runtime importance.
- `common_action_event`: `P1-medium` - Action event table is smaller but frequently used by N5/N6 reports and historical metadata repairs.

## Existing Index Posture

### `common_trigger_match`

- `common_trigger_match_output_event_id_key`: `CREATE UNIQUE INDEX common_trigger_match_output_event_id_key ON public.common_trigger_match USING btree (output_event_id)`
- `common_trigger_match_pkey`: `CREATE UNIQUE INDEX common_trigger_match_pkey ON public.common_trigger_match USING btree (trigger_match_id)`
- `common_trigger_match_run_id_source_event_id_asset_kind_iden_key`: `CREATE UNIQUE INDEX common_trigger_match_run_id_source_event_id_asset_kind_iden_key ON public.common_trigger_match USING btree (run_id, source_event_id, asset_kind, identity_key, direction, signal_type, condition_key, trigger_period, trigger_bucket)`
- `idx_common_trigger_match_identity`: `CREATE INDEX idx_common_trigger_match_identity ON public.common_trigger_match USING btree (for_trade_date, asset_kind, identity_key, trigger_time DESC)`
- `idx_common_trigger_match_run`: `CREATE INDEX idx_common_trigger_match_run ON public.common_trigger_match USING btree (run_id, output_event_type, created_at)`

### `common_trigger_state`

- `common_trigger_state_pkey`: `CREATE UNIQUE INDEX common_trigger_state_pkey ON public.common_trigger_state USING btree (trigger_state_id)`
- `common_trigger_state_run_id_for_trade_date_asset_kind_ident_key`: `CREATE UNIQUE INDEX common_trigger_state_run_id_for_trade_date_asset_kind_ident_key ON public.common_trigger_state USING btree (run_id, for_trade_date, asset_kind, identity_key, direction, signal_type, condition_key, trigger_period, trigger_bucket)`
- `idx_common_trigger_state_event`: `CREATE INDEX idx_common_trigger_state_event ON public.common_trigger_state USING btree (last_source_event_id)`
- `idx_common_trigger_state_lookup`: `CREATE INDEX idx_common_trigger_state_lookup ON public.common_trigger_state USING btree (run_id, asset_kind, identity_key, current_status)`

### `stock_trigger_context_snapshot`

- `idx_stock_trigger_context_lookup`: `CREATE INDEX idx_stock_trigger_context_lookup ON public.stock_trigger_context_snapshot USING btree (run_id, stock_identity_key, direction, condition_key)`
- `idx_stock_trigger_context_signal`: `CREATE INDEX idx_stock_trigger_context_signal ON public.stock_trigger_context_snapshot USING btree (run_id, direction, allowed_signal_types)`
- `stock_trigger_context_snapsho_run_id_source_condition_run_i_key`: `CREATE UNIQUE INDEX stock_trigger_context_snapsho_run_id_source_condition_run_i_key ON public.stock_trigger_context_snapshot USING btree (run_id, source_condition_run_id, stock_identity_key, lane, direction, condition_key)`
- `stock_trigger_context_snapsho_run_id_source_minute_target_s_key`: `CREATE UNIQUE INDEX stock_trigger_context_snapsho_run_id_source_minute_target_s_key ON public.stock_trigger_context_snapshot USING btree (run_id, source_minute_target_scope_id)`
- `stock_trigger_context_snapshot_pkey`: `CREATE UNIQUE INDEX stock_trigger_context_snapshot_pkey ON public.stock_trigger_context_snapshot USING btree (trigger_context_id)`

### `common_action_event`

- `common_action_event_event_id_key`: `CREATE UNIQUE INDEX common_action_event_event_id_key ON public.common_action_event USING btree (event_id)`
- `common_action_event_pkey`: `CREATE UNIQUE INDEX common_action_event_pkey ON public.common_action_event USING btree (action_event_row_id)`
- `common_action_event_run_id_action_key_key`: `CREATE UNIQUE INDEX common_action_event_run_id_action_key_key ON public.common_action_event USING btree (run_id, action_key)`
- `common_action_event_run_id_dedup_key_key`: `CREATE UNIQUE INDEX common_action_event_run_id_dedup_key_key ON public.common_action_event USING btree (run_id, dedup_key)`
- `idx_common_action_event_canonical_state`: `CREATE INDEX idx_common_action_event_canonical_state ON public.common_action_event USING btree (run_id, event_type, action_state, created_at)`
- `idx_common_action_event_identity`: `CREATE INDEX idx_common_action_event_identity ON public.common_action_event USING btree (for_trade_date, asset_kind, identity_key, created_at DESC)`
- `idx_common_action_event_run_type`: `CREATE INDEX idx_common_action_event_run_type ON public.common_action_event USING btree (run_id, event_type, created_at)`

## Static Reference Summary

- Files with hotspot references: `41`
- `common_trigger_match` files: `32`
- `common_trigger_state` files: `31`
- `stock_trigger_context_snapshot` files: `7`
- `common_action_event` files: `25`

## Query Shape Audit Plan

### `common_trigger_match`
- `CTM-1`: `run_id/output_event_type/created_at`; current index hint `idx_common_trigger_match_run`; next action: EXPLAIN-only verify N4/N5 lineage and outbox-join reports use this index.
- `CTM-2`: `for_trade_date/asset_kind/identity_key/trigger_time`; current index hint `idx_common_trigger_match_identity`; next action: EXPLAIN-only verify detail drawer/status monitor style lookups.
- `CTM-3`: `run_id/source_event_id/identity/signal/condition/period/bucket`; current index hint `unique dedup index`; next action: EXPLAIN-only verify execute/dedup path does not devolve to seq scan.
### `common_trigger_state`
- `CTS-1`: `run_id/asset_kind/identity_key/current_status`; current index hint `idx_common_trigger_state_lookup`; next action: EXPLAIN-only verify active/status monitor queries.
- `CTS-2`: `last_source_event_id`; current index hint `idx_common_trigger_state_event`; next action: EXPLAIN-only verify event id lookup paths.
### `stock_trigger_context_snapshot`
- `STCS-1`: `run_id/stock_identity_key/direction/condition_key`; current index hint `idx_stock_trigger_context_lookup`; next action: EXPLAIN-only verify N4 context fetch path.
- `STCS-2`: `run_id/direction/allowed_signal_types`; current index hint `idx_stock_trigger_context_signal`; next action: Validate whether ARRAY btree index is useful for actual predicates; consider GIN or predicate rewrite only in a future schema gate.
- `STCS-3`: `run_id/source_minute_target_scope_id`; current index hint `unique source_minute_target_scope_id index`; next action: EXPLAIN-only verify rollback/context lineage checks.
### `common_action_event`
- `CAE-1`: `run_id/event_type/action_state/created_at`; current index hint `idx_common_action_event_canonical_state`; next action: EXPLAIN-only verify N5/N6 stats and UI lineage queries.
- `CAE-2`: `for_trade_date/asset_kind/identity_key/created_at`; current index hint `idx_common_action_event_identity`; next action: EXPLAIN-only verify detail lookups.
- `CAE-3`: `run_id/dedup_key or run_id/action_key`; current index hint `unique dedup/action key indexes`; next action: EXPLAIN-only verify execute/repair scope probes.

## Remediation Strategy

Do not create indexes or rewrite queries from aggregate stats alone. The next step must be an EXPLAIN-only contract that maps representative query shapes to source files, records estimated rows and index choices, and keeps all operations read-only.

Allowed now:

- Document hotspot evidence and priority.
- Define EXPLAIN-only follow-up gates.
- Define index-review acceptance criteria.

Not allowed now:

- `CREATE INDEX`, `DROP INDEX`, or `ALTER TABLE`.
- `EXPLAIN ANALYZE` unless separately authorized.
- N3/N4/N5 runner execute.
- Outbox/inbox/checkpoint consumption or update.
- Worker startup.
- delivery/push/voice/mobile/sim/position/PnL/real_trade/proposal/order/trade.

## P0/P1/P2

- P0: `0`
- P1: `4` - each hotspot table requires EXPLAIN-only follow-up.
- P2: `1` - current stats are historical aggregates; exact historical timestamp attribution remains limited to audited probes.

## Forbidden Scope Proof

- DB write: `false`
- Schema/index migration: `false`
- Runner execute: `false`
- Rollback execute: `false`
- Outbox/inbox/checkpoint mutation: `false`
- Worker started: `false`
- delivery/push/voice/mobile: `false`
- sim/position/PnL/real_trade: `false`
- proposal/order/trade: `false`

## Next Gate Recommendation

`N3_N4_N5_RUNTIME_HOTSPOT_EXPLAIN_AUDIT_CONTRACT_GATE`

## Validation

- JSON parse: `PASS`
- Static reference scan: `PASS`
- Read-only catalog probe: `PASS`
- `git diff --check`: `PASS`
