# N5 Worker Scoped Consumption Smoke Readiness

Result: `READINESS_PASS`

Generated at: `2026-06-10T16:13:32+08:00`

Layer role: `runtime_control`

This gate is readiness-only. It did not start a worker, did not execute N5, did not write database rows, did not consume or update N4 outbox/inbox/checkpoint, and did not enter N6.

## Target

- Source N4 run: `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- Source layer / event: `N4_trigger` / `TriggerMatched`
- Proposed smoke run: `n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe`
- Proposed consumer: `n5_action_worker_v1_scoped_consumption_smoke_probe`
- Proposed mode: `consumption_only`
- Proposed max events: `50`
- Status JSON: `docs/N5_WORKER_SCOPED_CONSUMPTION_SMOKE_STATUS.json`
- Stop file: `tmp/n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe.stop`

## Prerequisite Proof

- N4 worker rollout registration refresh: `REGISTRATION_PASS`
- N4 day-scope bounded consumption smoke: `POST_REVIEW_PASS`
- N5 run-once unified output retry post-review: `POST_REVIEW_PASS`
- N5 HINT source-condition agnostic spec: `SPEC_PASS`
- N4 source run post-review: `POST_REVIEW_PASS`
- N3 action-confirmation metric post-review: `POST_REVIEW_PASS`
- Current policy still forbids long-running worker, N4 outbox status update, and N5 action fact/event writes in this scoped consumption-only smoke.

## N5 Source Readiness Proof

Live read-only proof for the target N4 source outbox:

```text
TriggerMatched total/pending/delivered/delivering = 556/556/0/0
TriggerPendingMarketData = 0
TriggerStateChanged = 0
distinct event_id / dedup_key / partition_key = 556/556/541
envelope fields present = 556/556
N4 outbox remains pending; delivered/delivering = 0/0
```

Unified payload readiness:

```text
condition_signal_type = 556/556
requested_periods = 556/556
triggered_period_details = 556/556
runtime_signal_type = 556/556
projection_30m_* trace fields = 556/556
period_trigger_baseline_trace = 556/556
trigger_mark_candidate = 556/556
condition_key / original_condition_key = 556/556
trigger_price = 556/556
trigger_live=true = 556/556
n5_entry_allowed=true = 556/556
canonical runtime signal_type B_BUY/S_SELL = 556/556
invalid BUY_HINT/SELL_HINT runtime signal = 0
action_mark emitted by N4 = 0
```

Lineage note:

```text
prior N5 run-once consumer inbox rows for this source = 556
target scoped smoke consumer inbox rows for this source = 0
blocking = false
```

## Target Baseline Clean Proof

The proposed N5 scoped smoke target baseline is clean:

```text
common_action_run = 0
common_action_quality_item = 0
stock/index/board_action_fact = 0/0/0
common_action_event = 0
common_event_outbox = 0
common_event_inbox = 0
common_event_consumer_checkpoint = 0
N6/user/downstream refs = 0
active worker heartbeat/status evidence = 0
```

## Proposed Scoped Consumption Smoke

If a later contract/final gate authorizes execute, the smoke must remain consumption-only:

```text
common_action_run = 1
common_action_quality_item = as planned by contract
common_event_inbox <= 50
common_event_consumer_checkpoint <= accepted partitions
stock/index/board_action_fact = 0/0/0
common_action_event = 0
common_event_outbox = 0
N4 outbox status update = 0
N6/user refs = 0
```

No semantic action outputs are allowed in this smoke:

```text
ActionExecuted = 0
ActionBlocked = 0
ActionEligible = 0
ActionSkipped = 0
HintEvent / RiskEvent / PositionEvent = 0
```

## Safety Requirements

- Future execute must have contract, dry-run, preflight, final gate, exact rollback SQL, and user confirmation.
- The smoke must be bounded by `max_events`, `max_runtime_seconds`, `heartbeat_interval_seconds`, `stop_file`, and `status_json`.
- It must not update or consume N4 outbox.
- It must not write action facts, action events, or N5 outbox.
- It must not enter N6, delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, or trade.
- If the next contract cannot prove a dedicated consumption-only N5 smoke path, it must block for runner alignment.

## Rollback Planning

Future rollback must be generated before execute:

```text
sql/N5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe_rollback.sql
```

It must hard-fail before the first `DELETE` or `UPDATE`, be scoped by the exact smoke run and consumer, guard N4/N5 delivered or delivering outbox rows, guard N6/user/delivery/sim/order/trade/position refs, preserve N4 trigger facts/outbox status and existing N5 run-once lineage, preserve N3/N2/N1 facts, and contain no `CASCADE`, `DROP`, or `TRUNCATE`.

Rollback is not authorized by this gate.

## Quality

```text
P0 = 0
P1 = 3
P2 = 0
```

P1 items:

1. `partition_key` is present for `556/556` source events, but distinct partition key count is `541`, not `556`; this matches prior N5 checkpoint partition cardinality and is not a readiness blocker.
2. A prior N5 run-once consumer already has `556` inbox rows for this source; the proposed smoke consumer baseline is still clean.
3. The visible N5 runner is run-once action-confirmation oriented; the next contract must prove or align a dedicated consumption-only smoke path.

## Decision

`READINESS_PASS`

This readiness allows entering `N5_WORKER_SCOPED_CONSUMPTION_SMOKE_CONTRACT_GATE`.

It does not authorize long-running worker startup, N4 outbox status updates, N4 outbox consumption, N5 action confirmation execute, N5 action fact/event/outbox writes, N6, delivery, sim, or trade.

## Validation

```text
JSON parse = PASS
referenced artifacts parse = PASS
live N4 source readiness proof = PASS
target baseline proof = PASS
payload unified field proof = PASS
N5 HINT policy consistency = PASS
forbidden scope proof = PASS
git diff --check = PASS
```

## Recommended Next Gate

`N5_WORKER_SCOPED_CONSUMPTION_SMOKE_CONTRACT_GATE`
