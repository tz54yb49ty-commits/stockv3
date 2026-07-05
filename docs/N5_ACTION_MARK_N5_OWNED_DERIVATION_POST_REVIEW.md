# N5 Action Mark N5-Owned Derivation Post-Review

Result: `POST_REVIEW_PASS`

Generated at: `2026-06-13T08:35:00+08:00`

## Implementation Proof

- Implementation result: `IMPLEMENTATION_PASS`
- Final `action_mark` owner: `N5_action`
- Canonical source: `n5_action_confirmation_metric`
- Basis: `previous_day_same_window_amount`
- N4 `trigger_mark_candidate` policy: trace-only

## N5-Owned Action Mark Proof

N5 now exposes `derive_final_action_mark_from_n5_metric(signal_type, metric)` in `src/ashare_v3/action/dry_run.py`.

Key code points:

- `src/ashare_v3/action/dry_run.py:525` defines `derive_final_action_mark_from_n5_metric`.
- `src/ashare_v3/action/dry_run.py:531` defines `derive_action_mark_decision_from_n5_metric`.
- `src/ashare_v3/action/dry_run.py:243` calls the N5 metric decision path while building candidates.
- `action_mark_source=n5_action_confirmation_metric`.
- `action_mark_basis=previous_day_same_window_amount`.

Rules:

- `B_BUY` -> `30m_volume` only when `buy_30m_price_pass=true` and `current_30m_virtual_amount > previous_day_same_window_amount`.
- `S_SELL` -> `30m_shrink` only when `sell_30m_price_pass=true` and `current_30m_virtual_amount < previous_day_same_window_amount`.
- Otherwise final `action_mark=normal`.

## N4 Trace-Only Proof

N4 `trigger_mark_candidate` is retained for trace only:

- `src/ashare_v3/action/dry_run.py:1135` writes `n4_trigger_mark_candidate`.
- It is no longer the source of final `action_mark`.

## previous_day_same_window_amount Proof

`previous_day_same_window_amount` means the previous trading day's same 30-minute time-window amount. It is not `previous_30m_full_amount`.

N3 metric support:

- `src/ashare_v3/market/realtime_virtual_metric.py:74` includes the DB metric field.
- `src/ashare_v3/market/realtime_virtual_metric.py:326` defines the helper.
- `src/ashare_v3/market/realtime_virtual_metric.py:615` writes the realtime virtual metric field.
- `src/ashare_v3/market/action_confirmation_projection_plan.py:586` writes the action-confirmation projection field.

Missing policy:

- Missing `previous_day_same_window_amount` does not block `ActionExecuted`.
- It downgrades `action_mark` to `normal`.
- Trace writes `action_mark_reason=previous_day_same_window_amount_missing`.

## Validation Summary

- Targeted N5/N3 tests: `137 OK`
- `test_n5*.py`: `5 OK`
- Implementation JSON parse: `PASS`
- `compileall`: `PASS`
- `scripts/check_n4_contract.py`: `PASS`, finding count `0`
- `git diff --check`: `PASS`

Broader residual caveat:

- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_action*.py'`
- Result: `119 tests`, `1 failure`
- Failing test: `test_action_schema_migration_review.ActionSchemaMigrationReviewTest.test_current_action_schema_migration_review_reports_canonical_payload_divergence`
- Failure: `AssertionError: 'source_trigger_state_id' not found in []`
- Classification: residual unrelated schema migration review assertion, not caused by N5-owned `action_mark` derivation.

## Forbidden Scope Proof

- N4 runner executed: `false`
- N5 runner executed: `false`
- DB written: `false`
- Outbox/inbox/checkpoint consumed or updated: `false`
- Worker started: `false`
- N6 entered: `false`
- Voice/mobile touched: `false`
- Sim/position/PnL/real trade touched: `false`
- Proposal/order/trade touched: `false`

## Decision

N5 final `action_mark` ownership is registered. N4 `trigger_mark_candidate` is trace-only. This gate is complete.

Next recommended gate: `V3_20260612_N4_N5_RUNTIME_REPLAY_AFTER_N5_ACTION_MARK_ALIGNMENT_READINESS_GATE`

## Next Prompt

```text
layer_role=runtime_control。

进入 V3_20260612_N4_N5_RUNTIME_REPLAY_AFTER_N5_ACTION_MARK_ALIGNMENT_READINESS_GATE。

目标：在 N5 final action_mark owned derivation 已 POST_REVIEW_PASS 后，只读复核 20260612 N4/N5 runtime replay/readiness artifacts 是否需要按 N5-owned action_mark 口径刷新；不得执行 N4/N5 runner，不写数据库，不消费/update outbox/inbox/checkpoint，不启动 worker，不进入 N6/voice/mobile/sim/position/order/trade。
```
