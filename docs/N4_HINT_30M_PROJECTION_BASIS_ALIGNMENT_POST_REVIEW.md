# N4 HINT 30m Projection Basis Alignment Post-Review

Result: `POST_REVIEW_PASS`

Reviewed at: `2026-06-13T11:49:49+08:00`

This runtime-control post-review is read-only. It did not execute N4, write database rows, consume/update outbox/inbox/checkpoint, start a worker, enter N5/N6, or touch voice/mobile/sim/position/order/trade.

## Implementation Proof

Implementation result: `ALIGNMENT_PASS`

Root cause: N4 HINT 30m projection still used the old side-specific 5m amount flags, while N5 final `action_mark` uses the N3 amount basis:

```text
current_30m_virtual_amount
previous_day_same_window_amount
```

The repaired N4 rule is:

- `BUY_HINT`: `buy_30m_price_pass=true` and `current_30m_virtual_amount > previous_day_same_window_amount`
- `SELL_HINT`: `sell_30m_price_pass=true` and `current_30m_virtual_amount < previous_day_same_window_amount`
- missing or invalid `previous_day_same_window_amount` does not emit HINT `TriggerMatched`
- old `*_5m_amount_pass` no longer decides HINT 30m projection

## Trace Proof

N4 trace now carries:

- `current_30m_virtual_amount`
- `previous_day_same_window_amount`
- `previous_30m_full_amount`
- `projection_30m_amount_basis=previous_day_same_window_amount`

## N5 Boundary Proof

- N5 final `action_mark` policy was not changed.
- Final `action_mark` remains N5-owned.
- N4 `trigger_mark_candidate` remains trace/candidate context only.
- N4 `trigger_mark_candidate` is not the final `action_mark` source.

## Validation Summary

Fresh verification run:

- `PYTHONPATH=src python3 -m unittest tests.test_trigger_action_confirmation_metric_matcher`: `19 OK`
- `PYTHONPATH=src python3 -m unittest tests.test_action_dry_run`: `33 OK`
- report JSON parse: `PASS`
- `PYTHONPATH=src python3 scripts/check_n4_contract.py`: `PASS`
- targeted `git diff --check`: `PASS`

## Forbidden Scope Proof

- N4 execute: `false`
- DB write: `false`
- worker started: `false`
- outbox consumed/updated: `false`
- inbox/checkpoint updated: `false`
- N5/N6 entered: `false`
- voice/mobile/sim/position/order/trade touched: `false`
- old system touched: `false`

## Decision

N4 HINT 30m projection basis alignment is registered as `POST_REVIEW_PASS`.

Important boundary: this code alignment does not rewrite existing 20260612 N4/N5 facts. Applying the new HINT basis to 20260612 facts requires a separate replay/readiness gate with rollback or supersession planning.

## Next Prompt

```text
layer_role=runtime_control。

进入 V3_20260612_N4_HINT_BASIS_ALIGNED_REPLAY_READINESS_GATE。

目标：在 N4 HINT 30m projection basis alignment 已 POST_REVIEW_PASS 后，只读复核是否需要按新 HINT 口径刷新 20260612 N4 trigger replay 与下游 N5 action_mark aligned replay。确认现有 N3 metric rows、N4 source rows、N5 closeout 状态、rollback/supersession 路线和是否需要先 scoped rollback N5/N4。不得执行 N4/N5，不写数据库，不消费/update outbox/inbox/checkpoint，不启动 scheduler，不进入 N6/voice/mobile/sim/position/order/trade。
```
