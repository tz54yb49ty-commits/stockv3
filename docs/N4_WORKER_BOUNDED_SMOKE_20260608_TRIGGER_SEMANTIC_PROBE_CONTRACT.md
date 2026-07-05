# N4 Worker Bounded Smoke 20260608 Trigger Semantic Probe Contract

Result: `CONTRACT_PASS`

Gate: `N4_WORKER_BOUNDED_SMOKE_TRIGGER_SEMANTIC_CONTRACT_GATE`

Generated at: `2026-06-10T09:30:30+08:00`

## Contract Decision

The contract passes and may proceed to final execute confirmation.

The previous source/oracle mismatch has been repaired. Current semantic dry-run proof:

```text
selected source events=10
semantic evaluations=10
source/oracle intersection=10
TriggerMatched=10
TriggerPendingMarketData=0
TriggerStateChanged=0
```

## Scope

- `smoke_run_id=n4_worker_bounded_smoke_20260608_trigger_semantic_probe`
- `consumer_name=n4_trigger_worker_v1_bounded_smoke_semantic_probe`
- `semantic_smoke=true`
- `semantic_oracle_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- `max_events=10`
- `max_runtime_seconds=120`
- `heartbeat_interval_seconds=10`
- `status_json=docs/N4_WORKER_BOUNDED_SMOKE_20260608_TRIGGER_SEMANTIC_PROBE_STATUS.json`
- `stop_file=tmp/n4_worker_bounded_smoke_20260608_trigger_semantic_probe.stop`

## Contract Requirements

| requirement | result |
|---|---|
| readiness passed | PASS |
| source selection alignment passed | PASS |
| runner alignment passed | PASS |
| target baseline clean | PASS |
| selected source events all pending N3 `MarketSnapshotUpdated` | PASS |
| source/oracle intersection = 10 | PASS |
| planned `TriggerMatched > 0` | PASS |
| planned `TriggerMatched <= max_events` | PASS |
| fixture/oracle trace preserved | PASS |
| oracle read-only | PASS |
| no N3 outbox update | PASS |
| no N5/N6 | PASS |

## Planned Write Scope

If future execute is authorized:

| table | rows |
|---|---:|
| `common_trigger_run` | 1 |
| `common_trigger_quality_item` | 2 |
| `common_event_inbox` | 10 |
| `common_event_consumer_checkpoint` | 10 |
| `common_trigger_state` | 10 |
| `common_trigger_match` | 10 |
| `common_event_outbox` | 10 |

Only scoped N4 smoke rows may be written. N3 outbox status, oracle lineage, N5, and N6 must remain untouched.

## Rollback

Rollback SQL:

`sql/N4_worker_bounded_smoke_20260608_trigger_semantic_probe_rollback.sql`

Rollback proof:

- hard-fail before first executable `DELETE/UPDATE`
- scoped to exact `smoke_run_id`
- scoped to exact `consumer_name`
- guards N4 delivered/delivering
- guards N5/N6/user/sim/order/trade/position refs
- preserves N3 facts/outbox and oracle lineage
- rollback not executed

## Forbidden Scope Proof

This contract gate did not:

- execute smoke
- write DB
- consume/update N3 outbox
- enter N5/N6
- start worker
- touch delivery/push/voice/mobile
- touch sim/position/pnl/real_trade
- touch proposal/order/trade
- touch old system

## Next Gate

Allowed:

`N4_WORKER_BOUNDED_SMOKE_TRIGGER_SEMANTIC_EXECUTE_USER_CONFIRMATION_GATE`

