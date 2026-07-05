# V3 N3 30m Virtual Amount Policy Guard Implementation

Result: `IMPLEMENTATION_PASS`

## Summary

N3 action-confirmation metric paths now enforce the elapsed-ratio policy:

```text
current_virtual_amount =
  current_elapsed_amount / previous_day_same_elapsed_amount * previous_day_same_full_amount
```

This prevents old rows such as `current_30m_virtual_amount=8433135360` from passing writer/preflight validation when the stored value conflicts with N3 proof.

## Changes

- `action_confirmation_projection_plan.py`
  - `current_5m_virtual_amount` and `current_30m_virtual_amount` now use previous-day same-window elapsed-ratio calibration.
  - `raw_json.virtual_amount_policy` stores proof for 5m and 30m.
  - projection enrichment receives calibrated `current_30m_virtual_amount`.
  - metric-ready simulation requires `current_30m_virtual_amount` and `previous_day_same_window_amount`.

- `v3_realtime_virtual_metric_writer.py`
  - validates `current_30m_virtual_amount` against `trace_json/raw_json.virtual_amount_policy.periods.30m`.
  - blocks missing proof with `current_30m_virtual_amount_policy_proof_missing`.
  - blocks mismatch with `current_30m_virtual_amount_policy_mismatch`.

## Validation

```text
PYTHONPATH=src:scripts python3 -m unittest \
  tests.test_market_data_action_confirmation_projection_plan \
  tests.test_v3_realtime_virtual_metric_writer_runner \
  tests.test_trigger_action_confirmation_metric_matcher \
  tests.test_action_dry_run \
  tests.test_action_execute \
  tests.test_v3_20260612_full_day_replay_plan \
  tests.test_v3_realtime_virtual_metric_builder \
  tests.test_n3_projection_enrichment_implementation

Ran 164 tests OK
```

Additional validation:

```text
trigger test group: 150 OK
JSON parse: PASS
compileall: PASS
scripts/check_n4_contract.py: PASS
git diff --check: PASS
untracked/no-index whitespace check: PASS
```

Forbidden scope held: no DB writes, no rollback, no N4/N5/N6 execute, no outbox/inbox/checkpoint consumption/update, no scheduler/worker, no voice/mobile/sim/position/order/trade, and no old-system access.
