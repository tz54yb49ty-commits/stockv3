# N4_WORKER_BOUNDED_SMOKE_IDEMPOTENCY_DUPLICATE_RETRY_READINESS

Result: `READINESS_PASS`

Gate: `N4_WORKER_BOUNDED_SMOKE_IDEMPOTENCY_DUPLICATE_RETRY_READINESS_GATE`

Layer role: `runtime_control`

This gate was readiness-only. It did not generate a fixture, execute smoke, write database rows, consume or update N3 outbox, enter N5/N6, or start a worker.

## Prerequisite Proof

- planning: `PLANNING_PASS`
- scoped consumption smoke: `POST_REVIEW_PASS`
- expanded consumption smoke: `POST_REVIEW_PASS`
- TriggerMatched semantic smoke: `POST_REVIEW_PASS`
- Pending+StateChanged semantic fixture smoke: `POST_REVIEW_PASS`
- state persistence dedup fix: `FIX_PASS`
- semantic runner alignment: `ALIGNMENT_PASS`
- semantic source selection alignment: `ALIGNMENT_PASS`

N4 bounded smoke evidence is now present for:

- `TriggerMatched`
- `TriggerPendingMarketData`
- `TriggerStateChanged`

This is still not a long-running worker approval.

## Code Support Static Scan

Static scan confirms:

- semantic fixture support exists
- `previous_states` support exists
- transition plan support exists
- `existing_consume_keys` duplicate detection exists
- nonzero scoped baseline blocks execute
- stable `source_event_consume_key` exists
- checkpoint payload is scoped by `bounded_smoke_run_id`
- N3 outbox update path remains absent
- N5/N6 path remains absent

## Current Smoke Boundary Proof

Live read-only proof:

- N3 `MarketSnapshotUpdated pending=2155`
- N3 delivered/delivering=`0`
- no worker heartbeat table evidence

Existing smoke rows remain scoped:

| smoke | run/quality/state/match/outbox/inbox/checkpoint | selected source pending | N5 refs |
|---|---:|---:|---:|
| scoped consumption | `1/2/0/0/0/5/5` | `5` | `0` |
| expanded consumption | `1/2/0/0/0/50/50` | `50` | `0` |
| TriggerMatched semantic | `1/2/10/10/10/10/10` | `10` | `0` |
| Pending+StateChanged semantic | `1/2/6/0/8/6/6` | `6` | `0` |

N6/user refs total:

- user_projection_run/user_signal_projection/user_signal_card/user_notification_queue = `0/0/0/0`

## Coverage Gap

The next bounded smoke still needs to prove:

- duplicate source events already in inbox are skipped deterministically
- repeated run with the same smoke_run_id blocks on nonzero baseline
- same source events with a new consumer are processed only if explicitly allowed by contract
- retry after failed transaction leaves no partial rows and can rerun after baseline clean
- checkpoint idempotency per partition remains bounded and deterministic
- dedup_key / event_id stability is preserved
- N3 outbox status is not updated during duplicate/retry handling

## Proposed Next Smoke Scope

- smoke_run_id: `n4_worker_bounded_smoke_20260608_idempotency_duplicate_retry_probe`
- consumer_name: `n4_trigger_worker_v1_bounded_smoke_idempotency_retry_probe`
- source_run_id: `realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- source_event_type: `MarketSnapshotUpdated`
- source_trade_date: `20260608`
- max_events: `10`
- max_runtime_seconds: `120`
- heartbeat_interval_seconds: `10`
- status_json: `docs/N4_WORKER_BOUNDED_SMOKE_20260608_IDEMPOTENCY_DUPLICATE_RETRY_PROBE_STATUS.json`
- stop_file: `tmp/n4_worker_bounded_smoke_20260608_idempotency_duplicate_retry_probe.stop`

The next contract must explicitly choose `consumption_only` or `semantic_fixture` mode. If testing duplicate/retry, it must use scoped fixture or pre-existing scoped inbox rows only; it must not mutate upstream N3 outbox.

## Baseline Clean Proof

Target new run scoped rows are all zero:

- run/quality/state/match/outbox/inbox/checkpoint = `0/0/0/0/0/0/0`
- N5 refs: `0`
- N6/user refs: `0`
- active worker heartbeat evidence: `0`

## Required Safety Gates

- generate contract / dry-run / preflight / final gate before execute
- generate rollback SQL for exact run_id and consumer before execute
- keep max_events / max_runtime / status_json / stop_file bounded
- do not start long-running worker
- do not update or consume N3 outbox
- do not enter N5/N6
- do not delivery/push/voice/mobile
- do not sim/position/PnL/real_trade
- do not proposal/order/trade
- do not touch old system

## Quality

- P0/P1/P2 = `0/2/0`
- P1 items:
  - idempotency / duplicate / retry fixture or exact mode is intentionally not generated in readiness gate.
  - same-source-events new-consumer policy must be explicitly chosen in the next contract gate.

## Validation

- JSON parse: `PASS`
- live baseline proof: `PASS`
- current smoke boundary proof: `PASS`
- code support static scan: `PASS`
- downstream refs scan: `PASS`
- git diff --check: `PASS`

## Next Gate

`N4_WORKER_BOUNDED_SMOKE_IDEMPOTENCY_DUPLICATE_RETRY_CONTRACT_GATE`
