# N4 Worker Bounded Smoke Expanded Scope Readiness

Result: `READINESS_PASS`

Gate: `N4_WORKER_BOUNDED_SMOKE_EXPANDED_SCOPE_READINESS_GATE`

Generated at: `2026-06-10T08:19:42+08:00`

## Prerequisite Proof

- Scoped smoke post-review: `POST_REVIEW_PASS`
- Execute result: `EXECUTE_PASS`
- `bounded_smoke_only=true`
- `worker_started=false`
- `long_running_worker_started=false`
- Scoped smoke `P0/P1/P2=0/0/0`
- Runner alignment: `ALIGNMENT_PASS`
- JSONB serialization fix: `FIX_PASS`

## Existing Scoped Smoke Boundary

The completed scoped smoke rows remain present and clean:

| proof | value |
|---|---:|
| `common_trigger_run` | 1 |
| `common_trigger_quality_item` | 2 |
| `common_event_inbox` | 5 |
| `common_event_consumer_checkpoint` | 5 |
| `common_trigger_state` | 0 |
| `common_trigger_match` | 0 |
| `common_event_outbox` | 0 |

Source boundary:

- N3 `MarketSnapshotUpdated pending=2155`
- selected 5 source events still pending
- N3 outbox not consumed or updated
- N5/N6 refs = `0`

## Expanded Source Readiness

Target source:

- `source_layer=N3_market_data`
- `source_run_id=realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- `event_type=MarketSnapshotUpdated`
- `trade_date=20260608`

Readiness proof:

| proof | value |
|---|---:|
| total events | 2155 |
| pending | 2155 |
| delivered/delivering | 0 / 0 |
| event schema version present | 2155 / 2155 |
| event id present | 2155 / 2155 |
| dedup key present | 2155 / 2155 |
| partition key present | 2155 / 2155 |
| payload JSON present | 2155 / 2155 |

Expanded sample readiness for `max_events=50`:

| proof | value |
|---|---:|
| selected sample | 50 |
| envelope fields present | 50 / 50 |
| `snapshot_id` present | 50 / 50 |
| `subscription_id` present | 50 / 50 |
| `pull_plan_id` present | 50 / 50 |
| `data_quality_status` present | 50 / 50 |
| `source_adapter` present | 50 / 50 |
| `projection_trace` present | 0 / 50 |

`projection_trace=0/50` is a P1 warning, not a blocker for this consumption/inbox/checkpoint smoke. The next contract gate must keep this scope bounded and must not fabricate trigger transition events. A trigger-semantics smoke requires explicit N3 projection facts or a projection join.

## Proposed Expanded Smoke Scope

- `smoke_run_id=n4_worker_bounded_smoke_20260608_unified_output_expanded_probe`
- `consumer_name=n4_trigger_worker_v1_bounded_smoke_expanded_probe`
- `max_events=50`
- `max_runtime_seconds=120`
- `heartbeat_interval_seconds=10`
- `status_json=docs/N4_WORKER_BOUNDED_SMOKE_20260608_UNIFIED_OUTPUT_EXPANDED_PROBE_STATUS.json`
- `stop_file=tmp/n4_worker_bounded_smoke_20260608_unified_output_expanded_probe.stop`

Future execute may write only scoped N4 smoke rows:

- `common_trigger_run=1`
- `common_trigger_quality_item` as planned by contract
- `common_event_inbox <= 50`
- `common_event_consumer_checkpoint <= 50 partitions`
- `common_trigger_state / common_trigger_match / common_event_outbox` only according to dry-run plan

Future execute must not write/update:

- N3 outbox status
- N5/N6
- delivery/push/voice/mobile
- sim/position/order/trade/real_trade

## Expanded Baseline Clean Proof

Target expanded rows are all zero:

| table/ref | rows |
|---|---:|
| `common_trigger_run` | 0 |
| `common_trigger_quality_item` | 0 |
| `common_trigger_state` | 0 |
| `common_trigger_match` | 0 |
| `common_event_outbox` | 0 |
| `common_event_inbox` | 0 |
| `common_event_consumer_checkpoint` | 0 |
| N5 action refs | 0 |
| N6/user refs | 0 |
| position/sim refs | 0 |
| active N4 worker heartbeat rows | 0 |

## Required Safety Gates

- Must remain bounded.
- Must not long-run.
- Must not update N3 outbox status.
- Must not enter N5/N6.
- Must not consume/update N5 outbox.
- Must not start delivery/push/voice/mobile.
- Must not touch sim/position/pnl/real_trade.
- Must not touch old system.
- Rollback must be generated for exact expanded `smoke_run_id` and `consumer_name` before any execute.
- The next contract gate must preserve the P1 warning that source payloads are snapshot-only and therefore suitable only for a consumption/inbox/checkpoint smoke unless projection facts are explicitly joined.

## Rollback Requirement

Future rollback SQL must be generated at:

`sql/N4_worker_bounded_smoke_20260608_unified_output_expanded_probe_rollback.sql`

It must:

- hard-fail before first `DELETE/UPDATE`
- guard delivered/delivering outbox rows
- guard N5/N6/user/sim/order/trade/position refs
- delete only scoped expanded smoke rows
- preserve N3 facts and N3 outbox status
- contain no `CASCADE` / `DROP` / `TRUNCATE`

## Forbidden Scope Proof

This readiness gate did not:

- start worker
- execute N4
- write database
- consume/update N3 outbox
- enter N5/N6
- touch delivery/push/voice/mobile
- touch sim/position/pnl/real_trade
- touch proposal/order/trade
- touch old system

## Validation

- source JSON parse: `PASS`
- live DB source event readiness proof: `PASS`
- live DB expanded baseline proof: `PASS`
- existing scoped smoke boundary proof: `PASS`
- rollback requirement proof: `PASS`
- `git diff --check`: `PASS`

## Next Gate

`N4_WORKER_BOUNDED_SMOKE_EXPANDED_SCOPE_CONTRACT_GATE`
