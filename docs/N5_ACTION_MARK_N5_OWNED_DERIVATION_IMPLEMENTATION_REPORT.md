# N5 Action Mark N5-Owned Derivation Implementation Report

Result: IMPLEMENTATION_PASS

## Summary

N5 now derives final `action_mark` from N3 action-confirmation metric evidence instead of trusting N4 `trigger_mark_candidate`.

Canonical source:

- `action_mark_source=n5_action_confirmation_metric`
- `action_mark_basis=previous_day_same_window_amount`
- `current_30m_virtual_amount`
- `previous_day_same_window_amount`

N4 `trigger_mark_candidate` is retained as `n4_trigger_mark_candidate` trace only.

## Rules

- `B_BUY` with passed confirmation, buy-side 30m price pass, and `current_30m_virtual_amount > previous_day_same_window_amount` -> `30m_volume`.
- `S_SELL` with passed confirmation, sell-side 30m price pass, and `current_30m_virtual_amount < previous_day_same_window_amount` -> `30m_shrink`.
- Otherwise -> `normal`.
- Missing `previous_day_same_window_amount` does not block `ActionExecuted`; it downgrades `action_mark` to `normal` with `action_mark_reason=previous_day_same_window_amount_missing`.

## Scope Proof

- N5 confirmation status rules are unchanged.
- N5 no longer uses N4 `trigger_mark_candidate` as the canonical final mark source.
- N3 metric builders and schema drafts now expose `previous_day_same_window_amount`.
- No N4/N5 execute was run.
- No database write, outbox consumption, worker start, N6 entry, voice/mobile/sim/position/order/trade/real_trade path was executed.

## Validation

- `tests.test_action_dry_run`
- `tests.test_action_execute`
- `tests.test_action_consumer_run_once_dry_run`
- `tests.test_action_execute_preflight`
- `tests.test_v3_realtime_virtual_metric_builder`
- `tests.test_v3_realtime_virtual_metric_schema_contract`
- `tests.test_n3_action_confirmation_metric_materialization_execute`
- `tests.test_v3_realtime_virtual_metric_writer_runner`

