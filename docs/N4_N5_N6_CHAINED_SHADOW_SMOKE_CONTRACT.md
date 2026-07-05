# N4->N5->N6 Chained Shadow Smoke Contract

Result: `CONTRACT_PASS`

Gate: `N4_N5_N6_CHAINED_SHADOW_SMOKE_CONTRACT_GATE`  
Layer role: `runtime_control`  
Generated on: `2026-06-10`

## Contract Decision

This contract freezes the chained smoke as a bounded staged shadow chain:

```text
existing N4 TriggerMatched source
  -> new scoped N5 semantic action smoke
  -> new scoped N6 shadow projection smoke
```

The N4 leg is read-only source preservation. It does not write new N4 rows and does not update N4 outbox status. The proposed N4 run id remains reserved for lineage/baseline proof, but this contract does not authorize a new N4 semantic replay.

## Prerequisite Proof

| Proof | Status |
|---|---|
| Chained readiness | `READINESS_PASS` |
| N6 rollout registration | `REGISTRATION_PASS` |
| N6 rollback readiness | `READINESS_PASS` |
| N5 rollout registration refresh | `REGISTRATION_PASS` |
| N4 rollout registration refresh | `REGISTRATION_PASS` |

## Source Readiness Proof

| Source | Pending | Delivered | Delivering |
|---|---:|---:|---:|
| Existing N4 `TriggerMatched` source | 556 | 0 | 0 |

N4 outbox status update planned: `0`  
N5 outbox status update planned: `0`

## Metric Binding Proof

Metric run:

```text
action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
```

Expected selected deterministic join coverage: `50/50`. Opaque payload `action_confirmation` remains untrusted. This matches the already reviewed 50-event N5 semantic action smoke under the same N4 source and metric lineage.

## Dry-Run Summary

| Metric | Count |
|---|---:|
| Chain event count | 50 |
| N4 new trigger writes | 0 |
| N5 `ActionBlocked` | 50 |
| N5 `ActionExecuted` | 0 |
| N5 outbox pending after N5 leg | 50 |
| N6 projection rows after N6 leg | 50 |
| Notification queue rows | 0 |

`P0/P1/P2 = 0/0/0`

## Planned Staged Write Scope

N4 leg:

| Table | Planned Rows |
|---|---:|
| `common_trigger_run` | 0 |
| `common_trigger_quality_item` | 0 |
| `common_trigger_state` | 0 |
| `common_trigger_match` | 0 |
| `common_event_outbox` | 0 |
| `common_event_inbox` | 0 |
| `common_event_consumer_checkpoint` | 0 |

N5 leg:

| Table | Planned Rows |
|---|---:|
| `common_action_run` | 1 |
| `common_action_quality_item` | 0 |
| `stock_action_fact` | 0 |
| `index_action_fact` | 0 |
| `board_action_fact` | 50 |
| `common_action_event` | 50 |
| `common_event_outbox` | 50 |
| `common_event_inbox` | 50 |
| `common_event_consumer_checkpoint` | 50 |
| `common_position_state` | 0 |
| `common_position_event` | 0 |

N6 leg:

| Table | Planned Rows |
|---|---:|
| `user_projection_run` | 1 |
| `user_signal_projection` | 50 |
| `user_signal_card` | 50 |
| `user_notification_queue` | 0 |
| `user_signal_decision` | 0 |

Forbidden writes remain zero: N4/N5 outbox status updates, N5 outbox consumption, delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, trade, and old system writes.

## Rollback Proof

Rollback SQL:

```text
sql/N4_N5_N6_chained_shadow_smoke_20260608_probe_rollback.sql
```

Rollback is disabled by default and hard-fails before the first `DELETE` or `UPDATE`. If a future rollback final gate authorizes it, rollback must proceed in reverse order:

1. N6 projection rows.
2. N5 action rows and N5 outbox rows.

N4 source rows are preserved by this contract.

Rollback guards N4 source outbox delivered/delivering, scoped N5 outbox delivered/delivering, and N6/user/delivery/sim/order/trade/position refs. It contains no `CASCADE`, `DROP`, or `TRUNCATE`.

## Forbidden Scope Proof

- N4/N5/N6 executed by this gate: `false`.
- Database written by this gate: `false`.
- N4 outbox consumed or updated: `false`.
- N5 outbox consumed or updated: `false`.
- Worker started: `false`.
- Delivery/push/voice/mobile touched: `false`.
- Sim/position/PnL/real_trade touched: `false`.
- Proposal/order/trade touched: `false`.
- Old system touched: `false`.
- Rollback executed: `false`.

## Allowed Execute Command

```bash
set -euo pipefail
PYTHONPATH=src:scripts python3 scripts/run_action_consumer_once.py \
  --semantic-action-smoke \
  --smoke-run-id n4_n5_n6_chained_shadow_smoke_20260608_action_probe \
  --consumer-name n5_action_worker_v1_n4_n5_n6_chained_shadow_probe \
  --source-trigger-run-id trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry \
  --source-event-type TriggerMatched \
  --metric-run-id action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry \
  --max-events 50 \
  --max-runtime-seconds 300 \
  --heartbeat-interval-seconds 10 \
  --status-json docs/N4_N5_N6_CHAINED_SHADOW_SMOKE_N5_STATUS.json \
  --stop-file tmp/n4_n5_n6_chained_shadow_smoke_20260608_action_probe.stop \
  --json-report-path docs/N4_N5_N6_CHAINED_SHADOW_SMOKE_N5_EXECUTE_REPORT.json \
  --markdown-report-path docs/N4_N5_N6_CHAINED_SHADOW_SMOKE_N5_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N4_N5_N6_chained_shadow_smoke_20260608_probe_rollback.sql \
  --execute \
  --user-confirmed
PYTHONPATH=src:scripts python3 scripts/run_n6_projection_once.py \
  --projection-run-id n4_n5_n6_chained_shadow_smoke_20260608_projection_probe \
  --source-action-run-id n4_n5_n6_chained_shadow_smoke_20260608_action_probe \
  --contract-json-path docs/N4_N5_N6_CHAINED_SHADOW_SMOKE_CONTRACT.json \
  --preflight-json-path docs/N4_N5_N6_CHAINED_SHADOW_SMOKE_PREFLIGHT.json \
  --expected-n5-outbox-count ActionBlocked:pending=50 \
  --execute \
  --user-confirmed \
  --json \
  > docs/N4_N5_N6_CHAINED_SHADOW_SMOKE_N6_EXECUTE_REPORT.json
```

## Decision

Allows next gate: `N4_N5_N6_CHAINED_SHADOW_SMOKE_EXECUTE_USER_CONFIRMATION_GATE`
