# N5 Action Confirmation V4 Repair Retry Execute Failure Review

Result: `FAILURE_REVIEW_PASS`

Gate: `N5_ACTION_CONFIRMATION_V4_REPAIR_RETRY_EXECUTE_FAILURE_REVIEW_GATE`

Layer role: `runtime_control`

This review is read-only. It did not execute N5, did not write action facts/events/outbox, did not consume or update N4 outbox/inbox/checkpoint, did not enter N6, did not start a worker, and did not execute rollback SQL.

## Target Runs

- N4 source run: `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry`
- N5 action run: `action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry`

## Failure Proof

The execute report exists and parses as JSON. The retry reached the N5 runner but failed before commit:

- result: `FAILED`
- classification: `BLOCKED / FAILED before commit`
- exception: `EventContractError`
- blocker: `n5_event_contract_rejects_30m_trigger_period_passthrough`
- failure stage: `build_n5_action_event -> validate_n5_trigger_fact_passthrough_payload`
- transaction committed: `false`

Error:

```text
N5 trigger fact passthrough payload must not include 30m in triggered_periods/all_trigger_periods/primary_trigger_period
```

## No Partial Write Proof

Live DB read-only post-check shows the target N5 scoped rows are all zero:

| Target | Rows |
|---|---:|
| `common_action_run` | 0 |
| `common_action_quality_item` | 0 |
| `stock_action_fact` | 0 |
| `index_action_fact` | 0 |
| `board_action_fact` | 0 |
| `common_action_event` | 0 |
| N5 `common_event_outbox` | 0 |
| N5 `common_event_inbox` | 0 |
| N5 consumer checkpoint | 0 |

Rollback is not required for the failed attempt because nothing was committed.

## Upstream Unchanged Proof

N4 remains unchanged:

| Proof | Count |
|---|---:|
| `common_trigger_run` | 1 |
| `common_trigger_match` | 119 |
| `common_trigger_state` | 3920 |
| N4 outbox total | 3920 |
| `TriggerMatched / pending` | 119 |
| `TriggerPendingMarketData / pending` | 3801 |
| delivered / delivering | 0 / 0 |

N3 remains preserved:

| Proof | Count |
|---|---:|
| `MarketSnapshotUpdated / total` | 2155 |
| `MarketSnapshotUpdated / pending` | 2155 |
| `MarketSnapshotUpdated / delivered` | 0 |
| `MarketSnapshotUpdated / delivering` | 0 |
| snapshot rows stock/index/board | 1945 / 83 / 127 |
| projection rows stock/index/board | 1945 / 83 / 127 |

## Semantic Diagnosis

Diagnosis: `N5_PASSTHROUGH_PAYLOAD_BUILDER_BUG`.

N4 is not the source of this failure. The N4 post-review already proved that `triggered_periods / all_trigger_periods / primary_trigger_period` contain no `30m`. A live N4 `TriggerMatched` sample confirms the legal HINT form:

```json
{
  "trigger_kind": "hint",
  "condition_key": "BUY_HINT",
  "original_condition_key": "BUY_HINT",
  "trigger_period": "30m",
  "triggered_periods": [],
  "all_trigger_periods": [],
  "primary_trigger_period": null,
  "trigger_mark_candidate": "30m_volume",
  "n5_entry_allowed": true,
  "trigger_price_present": true
}
```

The shared event guard in `src/ashare_v3/events/models.py` is also semantically correct: it accepts legal HINT 30m only when formal period fields are empty, and it rejects any `30m` inside `triggered_periods / all_trigger_periods / primary_trigger_period`.

The issue is in N5 payload construction. `src/ashare_v3/action/execute.py::build_action_event_passthrough_payload` falls back `primary_trigger_period` to `row/source trigger_period` when the source primary period is empty. For legal HINT 30m this reconstructs `primary_trigger_period=30m`, so `build_n5_action_event` correctly blocks the resulting invalid passthrough payload.

## Required Repair Direction

Next gate recommendation:

`N5_ACTION_EVENT_HINT_30M_PASSTHROUGH_CONTRACT_REPAIR_GATE`

Repair scope should be limited to:

- Fix N5 `event_factory` / `execute` HINT 30m passthrough payload construction.
- Keep `30m` only in `trigger_period`, projection trace, and `trigger_mark_candidate`.
- Do not put `30m` into `triggered_periods`, `all_trigger_periods`, or `primary_trigger_period`.
- Keep ordinary `trigger_kind=trigger + trigger_period=30m` rejected.
- Keep `TriggerPendingMarketData` quality-only / no-op.
- Add regression tests for legal HINT 30m passthrough and ordinary 30m rejection.

## Downstream Forbidden Proof

Live downstream refs remain zero:

| Target | Rows |
|---|---:|
| `user_projection_run` | 0 |
| `user_signal_projection` | 0 |
| `user_signal_card` | 0 |
| `user_notification_queue` | 0 |
| `common_position_state` | 0 |
| `common_position_event` | 0 |
| `user_sim_order` | 0 |
| `user_sim_trade` | 0 |
| `user_sim_position` | 0 |

No worker, delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, trade, rollback, or old-system action occurred in this gate.

## Validation

- JSON parse: `PASS`
- live DB no partial write proof: `PASS`
- N4 unchanged proof: `PASS`
- N3 preservation proof: `PASS`
- downstream refs scan: `PASS`
- semantic code trace: `PASS`
- `git diff --check`: `PASS`
