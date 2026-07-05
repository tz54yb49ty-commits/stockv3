# N3/N4/N5 Runtime Hotspot EXPLAIN Audit Execute Report

Result: `EXECUTE_PASS`  
Layer role: `runtime_control`  
Generated at: `2026-06-07T05:55:07.769797+00:00`

## Objective

Run read-only EXPLAIN FORMAT JSON for approved N3/N4/N5 hotspot query shapes and classify index/seq-scan risk.

## Read-Only Proof

- transaction_read_only: `on`
- EXPLAIN ANALYZE: `false`
- DB write: `false`
- Pre/post snapshot equal: `True`

## Summary

- Total shapes: `11`
- Index backed: `11`
- Seq scan expected small: `0`
- Seq scan risk: `0`
- Blocked unexpected plan: `0`

| Shape | Table | Classification | Indexes | Seq scan nodes | Plan rows | Total cost |
|---|---|---|---|---:|---:|---:|
| `CTM-1` | `common_trigger_match` | `index_backed` | `idx_common_trigger_match_run` | `0` | `1` | `4.45` |
| `CTM-2` | `common_trigger_match` | `index_backed` | `idx_common_trigger_match_identity` | `0` | `1` | `6.23` |
| `CTM-3` | `common_trigger_match` | `index_backed` | `idx_common_trigger_match_run` | `0` | `1` | `7.25` |
| `CTS-1` | `common_trigger_state` | `index_backed` | `idx_common_trigger_state_lookup` | `0` | `1` | `8.44` |
| `CTS-2` | `common_trigger_state` | `index_backed` | `idx_common_trigger_state_event` | `0` | `1` | `8.56` |
| `STCS-1` | `stock_trigger_context_snapshot` | `index_backed` | `idx_stock_trigger_context_lookup` | `0` | `1` | `8.44` |
| `STCS-2` | `stock_trigger_context_snapshot` | `index_backed` | `idx_stock_trigger_context_signal` | `0` | `1` | `746.36` |
| `STCS-3` | `stock_trigger_context_snapshot` | `index_backed` | `stock_trigger_context_snapsho_run_id_source_minute_target_s_key` | `0` | `1` | `8.43` |
| `CAE-1` | `common_action_event` | `index_backed` | `idx_common_action_event_canonical_state` | `0` | `15` | `219.01` |
| `CAE-2` | `common_action_event` | `index_backed` | `idx_common_action_event_identity` | `0` | `1` | `8.31` |
| `CAE-3` | `common_action_event` | `index_backed` | `common_action_event_run_id_dedup_key_key` | `0` | `1` | `8.56` |

## Seq Scan Risk Shapes

`[]`

## Forbidden Scope Proof

No DB write, EXPLAIN ANALYZE, schema/index migration, query rewrite, runner execute, rollback, outbox/inbox/checkpoint mutation, worker, delivery/push/voice/mobile, sim/position/PnL/real_trade, proposal/order/trade occurred.

## Next Gate Recommendation

`N3_N4_N5_RUNTIME_HOTSPOT_EXPLAIN_AUDIT_POST_REVIEW_GATE`
## Validation

- JSON parse: `PASS`
- Requirements assertion: `PASS`
- Forbidden scope assertion: `PASS`
- `git diff --check`: `PASS`
