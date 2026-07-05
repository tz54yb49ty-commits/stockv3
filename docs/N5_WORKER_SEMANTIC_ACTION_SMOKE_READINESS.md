# N5 Worker Semantic Action Smoke Readiness

Result: `BLOCKED`

Generated at: `2026-06-10T17:06:55+08:00`

Layer role: `runtime_control`

This gate is readiness-only. It did not execute N5, did not write action facts/events/outbox, did not consume or update N4/N5 outbox/inbox/checkpoint, did not enter N6, and did not start a worker.

## Target

- Source trigger run: `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- Source event type: `TriggerMatched`
- Required metric run: `action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- Proposed semantic smoke run: `n5_worker_semantic_action_smoke_20260608_unified_output_retry_probe`
- Proposed consumer: `n5_action_worker_v1_semantic_action_smoke_probe`
- Proposed mode: `action_confirmation_bounded_smoke`
- Proposed max events: `50`
- Status JSON: `docs/N5_WORKER_SEMANTIC_ACTION_SMOKE_STATUS.json`
- Stop file: `tmp/n5_worker_semantic_action_smoke_20260608_unified_output_retry_probe.stop`

## Prerequisite Proof

- N5 scoped consumption-only smoke: `POST_REVIEW_PASS`
- N5 run-once unified output retry: `POST_REVIEW_PASS`
- N5 HINT source-condition agnostic spec: `SPEC_PASS`
- N4 TriggerMatched source post-review: `POST_REVIEW_PASS`
- N3 action-confirmation metric post-review: `POST_REVIEW_PASS`
- Current policy still forbids N4 outbox status update, N5 outbox consumption, N6, delivery, sim, trade, and long-running worker startup.

## Source Readiness Proof

Live read-only proof for the target N4 source outbox:

```text
TriggerMatched total/pending/delivered/delivering = 556/556/0/0
TriggerPendingMarketData = 0
TriggerStateChanged = 0
distinct event_id / dedup_key / partition_key = 556/556/541
canonical runtime signal B_BUY/S_SELL = 556/556
invalid BUY_HINT/SELL_HINT runtime signal = 0
n5_entry_allowed=true = 556/556
N4 outbox status updated by this gate = false
```

## Metric Binding Proof

The required deterministic metric baseline exists and is suitable for a future semantic smoke:

```text
metric_run_id = action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
metric run count/status = 1/passed
metric rows stock/index/board/total = 412/60/84/556
metric_ready total = 556
deterministic join coverage = 556/556
duplicate metric grain = 0
opaque payload.action_confirmation trusted = false
```

P1 context: N3 does not write metric ids back into N4 payloads; N5 must bind this metric run by deterministic join policy. This is a known non-blocking contract rule for future semantic action execution.

## Target Baseline Proof

The proposed new semantic smoke target baseline is clean:

```text
common_action_run = 0
common_action_quality_item = 0
stock/index/board_action_fact = 0/0/0
common_action_event = 0
N5 common_event_outbox = 0
common_event_inbox = 0
common_event_consumer_checkpoint = 0
N6/user/downstream refs = 0
```

Existing N5 scoped consumption smoke rows remain scoped to `n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe` and are not a blocker for this new run id / consumer.

## Runner Readiness Proof

Source, metric, and target baseline are clean, but the current runner is not yet aligned for bounded semantic action smoke:

```text
consumption-only smoke path supports max_events/max_runtime/status_json/stop_file = true
semantic action-confirmation path supports bounded max_events = false
semantic action-confirmation path supports max_runtime/status_json/stop_file = false
semantic action-confirmation path reads all pending TriggerMatched rows = true
semantic action-confirmation path can be limited to 50 selected source rows = false
```

The CLI exposes bounded flags, but `run_action_consumer_once` only passes them into `run_consumption_only_smoke_once` when `--consumption-only-smoke` is set. The normal semantic action-confirmation path calls `fetch_current_real_pending_outbox_rows(...)` for the source run and does not accept `max_events`, `max_runtime_seconds`, `status_json`, or `stop_file` as enforceable bounded semantic controls.

## Proposed Semantic Action Smoke Scope

After a runner alignment gate, the next semantic smoke should be scoped as:

```text
smoke_run_id = n5_worker_semantic_action_smoke_20260608_unified_output_retry_probe
consumer_name = n5_action_worker_v1_semantic_action_smoke_probe
source_trigger_run_id = trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
source_event_type = TriggerMatched
metric_run_id = action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
max_events = 50
max_runtime_seconds = 120
heartbeat_interval_seconds = 10
status_json = docs/N5_WORKER_SEMANTIC_ACTION_SMOKE_STATUS.json
stop_file = tmp/n5_worker_semantic_action_smoke_20260608_unified_output_retry_probe.stop
```

Future planned writes, only after alignment plus contract/final gate/user confirmation:

```text
common_action_run = 1
common_action_quality_item = as planned by contract
stock/index/board_action_fact <= 50 total
common_action_event <= 50
N5 common_event_outbox <= 50
common_event_inbox <= 50
common_event_consumer_checkpoint <= accepted partitions
N4 outbox status update = 0
N6/user refs = 0
```

## Safety Requirements

- Future execute must have dry-run, contract, preflight, final gate, exact rollback SQL, and user confirmation.
- The semantic smoke runner must enforce `max_events`, `max_runtime_seconds`, `heartbeat_interval_seconds`, `stop_file`, and `status_json`.
- It must bind the required metric run id and use deterministic metric join, not opaque payload action-confirmation fields.
- It must keep all writes scoped to the new semantic smoke run id and consumer.
- It must not update or consume N4 outbox status.
- It must not enter N6 or delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, or trade.

## Rollback Planning

Future rollback must be generated before any execute:

```text
sql/N5_worker_semantic_action_smoke_20260608_unified_output_retry_probe_rollback.sql
```

It must hard-fail before the first `DELETE` or `UPDATE`, be scoped by exact smoke run id and consumer name, guard N4 source outbox status, guard N5 outbox delivered/delivering rows, guard N6/user/delivery/sim/order/trade/position refs, preserve N4/N3/N2/N1 facts and existing N5 lineages, and contain no `CASCADE`, `DROP`, or `TRUNCATE`.

Rollback is not authorized by this gate.

## Quality

```text
P0 = 2
P1 = 1
P2 = 0
```

P0 blockers:

1. `n5_semantic_action_bounded_runner_missing`
2. `n5_action_confirmation_runner_ignores_bounded_controls_and_reads_all_pending`

P1 item:

1. `metric_id_not_backfilled_to_n4_payload`: future semantic smoke must bind the deterministic metric run id by join policy.

## Decision

`BLOCKED`

This gate does not allow entering `N5_WORKER_SEMANTIC_ACTION_SMOKE_CONTRACT_GATE` yet. The correct next gate is:

```text
N5_WORKER_SEMANTIC_ACTION_SMOKE_RUNNER_ALIGNMENT_GATE
```

## Forbidden Scope Proof

```text
N5 executed = false
database written = false
N4/N5 outbox/inbox/checkpoint mutated = false
N6 entered = false
worker started = false
long-running worker started = false
delivery/push/voice/mobile = false
sim/position/pnl/real_trade = false
proposal/order/trade = false
old system touched = false
```

## Validation

```text
JSON parse = PASS
referenced artifacts parse = PASS
live source readiness proof = PASS
metric binding proof = PASS
target baseline proof = PASS
runner static capability proof = PASS
forbidden scope proof = PASS
git diff --check = PASS
```

## Recommended Next Gate

`N5_WORKER_SEMANTIC_ACTION_SMOKE_RUNNER_ALIGNMENT_GATE`
