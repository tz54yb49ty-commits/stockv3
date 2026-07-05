# N4->N5->N6 Chained Shadow Smoke Readiness

Result: `READINESS_PASS`

Gate: `N4_N5_N6_CHAINED_SHADOW_SMOKE_READINESS_GATE`  
Layer role: `runtime_control`  
Generated on: `2026-06-10`

## Scope

This gate is read-only. It did not execute N4, N5, or N6, did not write database rows, did not consume or update N4/N5 outbox or inbox/checkpoint rows, did not start a worker, and did not touch delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, trade, or the old system.

## Prerequisite Proof

| Artifact | Required | Observed |
|---|---:|---:|
| `docs/N6_PROJECTION_ROLLOUT_REGISTRATION.json` | `REGISTRATION_PASS` | `REGISTRATION_PASS` |
| `docs/N6_PROJECTION_ROLLBACK_READINESS.json` | `READINESS_PASS` | `READINESS_PASS` |
| `docs/N6_PROJECTION_BOUNDED_SMOKE_POST_REVIEW.json` | `POST_REVIEW_PASS` | `POST_REVIEW_PASS` |
| `docs/N5_WORKER_ROLLOUT_REGISTRATION_REFRESH.json` | `REGISTRATION_PASS` | `REGISTRATION_PASS` |
| `docs/N5_WORKER_LARGER_SCOPE_SEMANTIC_SMOKE_POST_REVIEW.json` | `POST_REVIEW_PASS` | `POST_REVIEW_PASS` |
| `docs/N4_N5_CHAINED_BOUNDED_SMOKE_POST_REVIEW.json` | `POST_REVIEW_PASS` | `POST_REVIEW_PASS` |
| `docs/N4_WORKER_BOUNDED_SMOKE_ROLLOUT_REGISTRATION_REFRESH.json` | `REGISTRATION_PASS` | `REGISTRATION_PASS` |

N4 bounded/day-scope evidence is registered. N5 scoped, semantic, larger-scope, and chained evidence is registered. N6 bounded shadow projection smoke is registered and has rollback readiness. Existing N4/N5/N6 smoke rows are registered evidence and are not blockers for a new scoped chained run because the proposed run identifiers are new.

## Source Readiness Proof

Live read-only transaction proof: `transaction_read_only=on`.

N4 source readiness:

| Source | Pending | Delivered | Delivering | Total |
|---|---:|---:|---:|---:|
| `TriggerMatched` from `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry` | 556 | 0 | 0 | 556 |

N5 action readiness:

| Source | Pending | Delivered | Delivering | Total |
|---|---:|---:|---:|---:|
| N5 larger-scope outbox from `n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe` | 200 | 0 | 0 | 200 |

N5 larger-scope event distribution:

| Event Type | Status | Count |
|---|---|---:|
| `ActionBlocked` | `pending` | 199 |
| `ActionExecuted` | `pending` | 1 |

N6 projection readiness:

| Existing Evidence Row Type | Count |
|---|---:|
| `user_projection_run` | 1 |
| `user_signal_projection` | 200 |
| `user_signal_card` | 200 |
| `user_notification_queue` | 0 |

N4 outbox status update is not authorized. N5 outbox status update is not authorized. N6 may only shadow-read N5 outbox in a future bounded contract, without status update.

## Proposed Chained Shadow Smoke Scope

Recommended mode: bounded staged `N4 -> N5 -> N6` shadow chain.

Proposed identifiers:

| Leg | Identifier |
|---|---|
| N4 trigger run | `n4_n5_n6_chained_shadow_smoke_20260608_trigger_probe` |
| N4 consumer | `n4_trigger_worker_v1_n4_n5_n6_chained_shadow_probe` |
| N5 action run | `n4_n5_n6_chained_shadow_smoke_20260608_action_probe` |
| N5 consumer | `n5_action_worker_v1_n4_n5_n6_chained_shadow_probe` |
| N6 projection run | `n4_n5_n6_chained_shadow_smoke_20260608_projection_probe` |

The contract gate must choose and freeze the exact N4 leg policy: either deterministic N4 semantic replay under the new N4 run id, or an explicitly read-only registered `TriggerMatched` source seed with no N4 status mutation. The later execute path, if authorized, must still use a new N5 `action_run_id` and a new N6 `user_projection_run_id`.

Expected high-level staged scope if future execute is authorized:

| Leg | Allowed Scoped Writes | Forbidden |
|---|---|---|
| N4 | `common_trigger_run`, quality, state, match, N4 outbox | N3 outbox update, N5/N6 writes |
| N5 | action run, quality, inbox/checkpoint, action facts/events, N5 outbox | N4 outbox update, N6 writes |
| N6 | projection run, signal projection, signal card | N5 outbox update, notification delivery, sim/trade |

The next contract gate must freeze exact commands, planned row counts, status JSON paths, stop files, and rollback SQL before any execute authorization.

## Target Baseline Clean Proof

N4 target baseline:

| Table | Count |
|---|---:|
| `common_trigger_run` | 0 |
| `common_trigger_quality_item` | 0 |
| `common_trigger_state` | 0 |
| `common_trigger_match` | 0 |
| `common_event_outbox` | 0 |
| `common_event_inbox` | 0 |
| `common_event_consumer_checkpoint` | 0 |

N5 target baseline:

| Table | Count |
|---|---:|
| `common_action_run` | 0 |
| `common_action_quality_item` | 0 |
| `stock_action_fact` | 0 |
| `index_action_fact` | 0 |
| `board_action_fact` | 0 |
| `common_action_event` | 0 |
| `common_event_outbox` | 0 |
| `common_event_inbox` | 0 |
| `common_event_consumer_checkpoint` | 0 |
| `common_position_state` | 0 |
| `common_position_event` | 0 |

N6 target baseline:

| Table | Count |
|---|---:|
| `user_projection_run` | 0 |
| `user_signal_projection` | 0 |
| `user_signal_card` | 0 |
| `user_notification_queue` | 0 |

Downstream refs for the proposed identifiers are zero or the optional downstream tables are absent. `user_signal_decision`, `common_position_state`, and `common_position_event` are all `0` for the proposed identifiers.

## Safety Requirements

- Every execute must remain bounded by `max_events`, `max_runtime_seconds`, `heartbeat_interval_seconds`, `stop_file`, and `status_json`.
- The contract gate must generate contract, dry-run, preflight, final gate review, and rollback SQL before any execute.
- No long-running worker is authorized.
- No N4 or N5 outbox status update is authorized.
- N6 may only shadow-read N5 outbox, without consuming or updating it.
- No delivery, push, voice, or mobile path is authorized.
- No sim, position, PnL, real trade, proposal, order, or trade path is authorized.
- Existing smoke rows remain registered evidence and must not be silently deleted.

## Rollback Planning

Rollback must be reverse-order aware:

1. N6 projection rows.
2. N5 action rows and N5 outbox rows.
3. N4 trigger rows and N4 outbox rows.

Rollback must be scoped by the exact N4 run id and consumer, N5 action run id and consumer, and N6 user projection run id. It must guard N4 outbox delivered/delivering, N5 outbox delivered/delivering, N6/user refs, delivery refs, sim/order/trade/position refs, and preserve N5/N4/N3/N2/N1 source facts plus existing smoke lineages.

Rollback is not executable in this gate. A separate rollback final gate and user confirmation would be required.

## Forbidden Scope Proof

- SQL executed: read-only `SELECT` only.
- Database written: `false`.
- N4/N5/N6 execute: `false`.
- Outbox/inbox/checkpoint consumed or updated: `false`.
- Worker started: `false`.
- Delivery/push/voice/mobile touched: `false`.
- Sim/position/PnL/real_trade touched: `false`.
- Proposal/order/trade touched: `false`.
- Old system touched: `false`.

## P0/P1/P2

`P0/P1/P2 = 0/0/0`

## Decision

`READINESS_PASS`

The system is ready to enter `N4_N5_N6_CHAINED_SHADOW_SMOKE_CONTRACT_GATE`. This is not execute approval, not long-running worker approval, not N4/N5 outbox ack approval, and not delivery/sim/trade approval.

## Recommended Next Gate

`N4_N5_N6_CHAINED_SHADOW_SMOKE_CONTRACT_GATE`
