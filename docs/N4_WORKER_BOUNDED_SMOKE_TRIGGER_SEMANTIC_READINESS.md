# N4 Worker Bounded Smoke Trigger Semantic Readiness

Result: `READINESS_PASS`

Gate: `N4_WORKER_BOUNDED_SMOKE_TRIGGER_SEMANTIC_READINESS_GATE`

Generated at: `2026-06-10T09:04:41+08:00`

## Decision

The previous P0 blocker is cleared.

Former blocker:

`n4_worker_bounded_smoke_semantic_runner_not_oracle_or_fixture_wired`

Current proof:

- semantic runner alignment: `ALIGNMENT_PASS`
- runner supports `--semantic-smoke`
- runner supports `--semantic-fixture-path`
- runner supports `--semantic-oracle-run-id`
- execute path uses `semantic_inputs["evaluations"]`
- execute path uses `semantic_inputs["previous_states"]`
- fixture/oracle input without `--semantic-smoke` blocks before DB connect/write
- `--semantic-smoke` without fixture/oracle blocks before DB connect/write
- fixture/oracle-derived plans are tagged `fixture_only=true`
- fixture/oracle-derived plans are tagged `not_new_market_decision=true`

It is now allowed to enter:

`N4_WORKER_BOUNDED_SMOKE_TRIGGER_SEMANTIC_CONTRACT_GATE`

## P0/P1/P2

| severity | count |
|---|---:|
| P0 | 0 |
| P1 | 2 |
| P2 | 0 |

P1 notes:

- Existing N4 unified output retry oracle already has downstream N5/N6 refs. It can only be read as an immutable oracle; future semantic smoke must not mutate oracle facts or oracle outbox.
- Existing oracle covers `TriggerMatched` only. `TriggerPendingMarketData` and `TriggerStateChanged` require a deterministic fixture or a distinct oracle if they are included.

## Prerequisite Proof

| prerequisite | result |
|---|---|
| scoped smoke post-review | `POST_REVIEW_PASS` |
| expanded smoke post-review | `POST_REVIEW_PASS` |
| trigger semantic runner alignment | `ALIGNMENT_PASS` |
| JSONB serialization fix | `FIX_PASS` |
| unified N4 oracle post-review | `POST_REVIEW_PASS` |

The completed scoped and expanded smokes remain bounded:

- `worker_started=false`
- `long_running_worker_started=false`
- N3 outbox status not updated
- N5/N6 refs from those smoke probes = `0`

## Runner Capability Proof

Static runner/code proof:

| proof | value |
|---|---|
| `--semantic-smoke` flag present | true |
| `--semantic-fixture-path` flag present | true |
| `--semantic-oracle-run-id` flag present | true |
| execute uses semantic evaluations | true |
| execute uses semantic previous states | true |
| `require_semantic_inputs` called before DB connect | true |
| fixture without semantic mode guard | true |
| semantic mode without fixture/oracle guard | true |
| guard tests present | true |
| `fixture_only` tag present | true |
| `not_new_market_decision` tag present | true |

The runner capability gap from the previous readiness gate is no longer present.

## Candidate Semantic Source

Read-only oracle:

`trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`

Live DB proof:

| proof | value |
|---|---:|
| oracle run exists/status | 1 / passed |
| `common_trigger_state` | 556 |
| `common_trigger_match` | 556 |
| N4 outbox `TriggerMatched/pending` | 556 |
| `TriggerPendingMarketData` | 0 |
| `TriggerStateChanged` | 0 |

Unified payload proof:

| field | coverage |
|---|---:|
| `condition_signal_type` | 556/556 |
| `requested_periods` | 556/556 |
| `triggered_period_details` | 556/556 |
| `runtime_signal_type` | 556/556 |
| `event_time` | 556/556 |
| `projection_30m_required` | 556/556 |
| `projection_30m_flag` | 556/556 |
| `projection_30m_type` | 556/556 |
| `n5_entry_allowed=true` | 556/556 |
| `action_mark` emitted by N4 | 0/556 |
| `trigger_price` missing | 0/556 |
| invalid `signal_type` | 0 |
| runtime signal mismatch | 0 |

`common_trigger_match.raw_json` unified field proof:

| field | coverage |
|---|---:|
| `condition_signal_type` | 556/556 |
| `requested_periods` | 556/556 |
| `triggered_period_details` | 556/556 |
| `runtime_signal_type` | 556/556 |
| `event_time` | 556/556 |
| `projection_30m_required` | 556/556 |
| `projection_30m_flag` | 556/556 |
| `projection_30m_type` | 556/556 |
| `trigger_price` present | 556/556 |
| `n5_entry_allowed=true` | 556/556 |

Condition signal distribution:

| condition_signal_type | rows |
|---|---:|
| `BUY` | 299 |
| `BUY_HINT` | 116 |
| `SELL` | 135 |
| `SELL_HINT` | 6 |

Downstream read-only note for oracle:

| downstream ref | rows |
|---|---:|
| `common_action_run` | 1 |
| `common_action_event` | 556 |
| `stock_action_fact` | 412 |
| `index_action_fact` | 60 |
| `board_action_fact` | 84 |
| `user_projection_run` | 1 |

These refs are not blockers for readiness because the semantic smoke must use the oracle read-only and write only its own scoped smoke rows.

## Target Semantic Baseline

Target semantic smoke:

- `smoke_run_id=n4_worker_bounded_smoke_20260608_trigger_semantic_probe`
- `consumer_name=n4_trigger_worker_v1_bounded_smoke_semantic_probe`

Live baseline is clean:

| table/ref | rows |
|---|---:|
| `common_trigger_run` | 0 |
| `common_trigger_quality_item` | 0 |
| `common_trigger_state` | 0 |
| `common_trigger_match` | 0 |
| `common_event_outbox` | 0 |
| `common_event_inbox` | 0 |
| `common_event_consumer_checkpoint` | 0 |

N3 source events remain available:

- N3 `MarketSnapshotUpdated` pending = `2155`

## Proposed Semantic Smoke Scope

Future contract should use:

- `smoke_run_id=n4_worker_bounded_smoke_20260608_trigger_semantic_probe`
- `consumer_name=n4_trigger_worker_v1_bounded_smoke_semantic_probe`
- `semantic_smoke=true`
- `semantic_oracle_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- `max_events<=10`
- `max_runtime_seconds<=120`
- `heartbeat_interval_seconds<=10`
- `status_json=docs/N4_WORKER_BOUNDED_SMOKE_20260608_TRIGGER_SEMANTIC_PROBE_STATUS.json`
- `stop_file=tmp/n4_worker_bounded_smoke_20260608_trigger_semantic_probe.stop`

Expected contract behavior:

- derive deterministic transition plans from the read-only oracle or a fixture
- tag derived plans as fixture/oracle-derived
- write only scoped smoke N4 rows if future execute is authorized
- exercise `TriggerMatched` state/match/outbox path
- preserve N3 outbox status
- preserve N5/N6/downstream state

If `TriggerPendingMarketData` or `TriggerStateChanged` must be included, the next contract must provide an explicit deterministic fixture or a separate oracle for those event types.

## Required Safety Gates

Next contract/preflight must enforce:

- semantic transition plans are deterministic and traceable
- no fabricated market-data decision
- oracle facts and oracle outbox are read-only
- fixture/oracle-derived rows are labeled
- rollback generated for exact `smoke_run_id` and `consumer_name`
- bounded execution only
- no long-running worker
- no N3 outbox update
- no N5/N6
- no delivery/push/voice/mobile
- no sim/position/pnl/real_trade
- old system untouched

## Forbidden Scope Proof

This readiness gate did not:

- start a worker
- execute N4
- write the database
- consume/update N3 outbox
- enter N5/N6
- touch delivery/push/voice/mobile
- touch sim/position/pnl/real_trade
- touch proposal/order/trade
- touch the old system

## Validation

- source JSON parse: `PASS`
- runner static semantic proof: `PASS`
- scoped/expanded post-review proof: `PASS`
- candidate semantic source proof: `PASS`
- semantic smoke baseline proof: `PASS`
- downstream refs scan: `PASS`
- rollback requirement proof: `PASS`
- `git diff --check`: `PASS`

## Next Gate

Allowed:

`N4_WORKER_BOUNDED_SMOKE_TRIGGER_SEMANTIC_CONTRACT_GATE`
