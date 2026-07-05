# N3/N4/N5 Runtime Hotspot EXPLAIN Audit Contract

Result: `CONTRACT_PASS`  
Layer role: `runtime_control`  
Generated at: `2026-06-07T05:48:33.333433+00:00`

## Objective

Define an EXPLAIN-only audit contract for local N3/N4/N5 runtime hotspot tables without running EXPLAIN, creating indexes, rewriting queries, or mutating database state.

## Scope

Hotspot tables:

- `common_trigger_match`
- `common_trigger_state`
- `stock_trigger_context_snapshot`
- `common_action_event`

Selected query shapes: `11`

| Shape | Table | Predicate family | Expected index |
|---|---|---|---|
| `CTM-1` | `common_trigger_match` | `run_id/output_event_type/created_at` | `idx_common_trigger_match_run` |
| `CTM-2` | `common_trigger_match` | `for_trade_date/asset_kind/identity_key/trigger_time` | `idx_common_trigger_match_identity` |
| `CTM-3` | `common_trigger_match` | `run_id/source_event_id/identity/signal/condition/period/bucket` | `common_trigger_match_run_id_source_event_id_asset_kind_iden_key` |
| `CTS-1` | `common_trigger_state` | `run_id/asset_kind/identity_key/current_status` | `idx_common_trigger_state_lookup` |
| `CTS-2` | `common_trigger_state` | `last_source_event_id` | `idx_common_trigger_state_event` |
| `STCS-1` | `stock_trigger_context_snapshot` | `run_id/stock_identity_key/direction/condition_key` | `idx_stock_trigger_context_lookup` |
| `STCS-2` | `stock_trigger_context_snapshot` | `run_id/direction/allowed_signal_types` | `idx_stock_trigger_context_signal` |
| `STCS-3` | `stock_trigger_context_snapshot` | `run_id/source_minute_target_scope_id` | `stock_trigger_context_snapsho_run_id_source_minute_target_s_key` |
| `CAE-1` | `common_action_event` | `run_id/event_type/action_state/created_at` | `idx_common_action_event_canonical_state, idx_common_action_event_run_type` |
| `CAE-2` | `common_action_event` | `for_trade_date/asset_kind/identity_key/created_at` | `idx_common_action_event_identity` |
| `CAE-3` | `common_action_event` | `run_id/dedup_key or run_id/action_key` | `common_action_event_run_id_dedup_key_key, common_action_event_run_id_action_key_key` |

## Run IDs

- N4 execute: `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- N4 context: `trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1`
- N5 action: `action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`

## Parameter Discovery

The next preflight/execute gate may run read-only parameter discovery `SELECT` statements only. These resolve one scoped sample for each hotspot family and must run with `default_transaction_read_only=on`.

## P0 Guards

- Any planned command contains EXPLAIN ANALYZE or ANALYZE.
- Any planned command contains INSERT/UPDATE/DELETE/MERGE/CREATE/ALTER/DROP/TRUNCATE/COPY/GRANT/REVOKE/VACUUM/REINDEX/CLUSTER.
- Any planned command references one of the five denied external display/membership tables.
- Any planned command consumes or updates outbox/inbox/checkpoint.
- Any planned command starts worker, delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, or trade flow.
- Any EXPLAIN audit entry lacks table, shape_id, source_files, SQL, plan JSON, top node, scan node summary, estimated rows, and index/seq-scan classification.

## Acceptance Criteria

- Dry-run must show current planning artifact parsed and all 11 query shapes selected.
- Next execute/audit gate must run parameter discovery SELECTs and EXPLAIN statements in default_transaction_read_only=on.
- EXPLAIN output must be FORMAT JSON and persisted as artifact only, not DB audit rows.
- Each shape must classify plan as index_backed, seq_scan_expected_small, seq_scan_risk, or blocked_unexpected_plan.
- No index recommendation may become executable until a separate migration contract/rollback gate.
- P0 must remain 0 before any index-review gate proceeds.

## Forbidden Scope Proof

- DB write: `false`
- EXPLAIN executed in this gate: `false`
- EXPLAIN ANALYZE: `false`
- Schema/index migration: `false`
- Query rewrite: `false`
- Runner execute: `false`
- Rollback execute: `false`
- Outbox/inbox/checkpoint mutation: `false`
- Worker started: `false`
- delivery/push/voice/mobile: `false`
- sim/position/PnL/real_trade: `false`
- proposal/order/trade: `false`

## P0/P1/P2

- P0: `0`
- P1: `4`
- P2: `1`

## Next Gate Recommendation

`N3_N4_N5_RUNTIME_HOTSPOT_EXPLAIN_AUDIT_PREFLIGHT_GATE`
