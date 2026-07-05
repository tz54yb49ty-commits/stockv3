# N4 Unified Trigger Signal Output Dry-Run Alignment Report

## Result

ALIGNMENT_PASS

## Scope

- layer_role: N4_trigger
- N4 execute: not run
- database writes: not run
- schema migration: not run
- outbox/inbox/checkpoint consumption or update: not run
- N5/N6: not entered
- worker: not started
- delivery/push/voice/mobile/sim/position/order/trade/real_trade: not touched
- old system: not touched

## Payload-Only Decision

The unified trigger signal output contract is implemented as payload-only for this gate.
No physical schema column was added, and no schema migration was drafted or executed.

The unified fields are emitted or mirrored through:

- N4 v4 dry-run plans and reports
- projection matcher dry-run plans and reports
- `common_event_outbox.payload_json`
- `common_trigger_state.raw_json`
- `common_trigger_match.raw_json`

## Unified Fields

All N4 output payload paths now carry the approved unified field set:

- `signal_type`
- `runtime_signal_type`
- `direction`
- `condition_signal_type`
- `condition_key`
- `original_condition_key`
- `trigger_kind`
- `trigger_mark_candidate`
- `requested_periods`
- `triggered_periods`
- `all_trigger_periods`
- `primary_trigger_period`
- `triggered_period_details`
- `trigger_period`
- `trigger_price`
- `trigger_time`
- `event_time`
- `price_source`
- `match_basis`
- `baseline_source`
- `projection_30m_required`
- `projection_30m_flag`
- `projection_30m_type`
- `projection_period`
- `projection_30m_volume_up_flag`
- `projection_30m_shrink_down_flag`
- `trigger_live`
- `current_status`
- `n5_entry_allowed`
- `data_quality_status`

## Six-Family Proof

The matcher now derives `condition_signal_type` for all six approved N2 condition families:

- `BUY` -> `signal_type=B_BUY`, `trigger_kind=trigger`, formal periods only.
- `SELL` -> `signal_type=S_SELL`, `trigger_kind=trigger`, formal periods only.
- `BUY:FULL` -> `signal_type=B_BUY`, `trigger_kind=trigger`, D-only formal trigger.
- `SELL:FULL` -> `signal_type=S_SELL`, `trigger_kind=trigger`, D-only formal trigger.
- `BUY_HINT` -> `signal_type=B_BUY`, `trigger_kind=hint`, legal `trigger_period=30m`, empty formal periods, `projection_30m_type=volume_up`.
- `SELL_HINT` -> `signal_type=S_SELL`, `trigger_kind=hint`, legal `trigger_period=30m`, empty formal periods, `projection_30m_type=shrink_down`.

`BUY_HINT` and `SELL_HINT` do not populate `triggered_periods`, `all_trigger_periods`, or `primary_trigger_period` with `30m`. They carry 30m evidence only in projection fields and trace.

## P0 Guard Proof

N4 v4 enforcement now blocks future `TriggerMatched` writes for:

- invalid or mismatched `signal_type` / `runtime_signal_type`
- missing or invalid `condition_signal_type`
- condition family mismatch between `condition_signal_type` and `condition_key`
- missing `condition_key` / `original_condition_key`
- missing `trigger_price`
- missing or false `n5_entry_allowed`
- formal matched rows without non-empty `requested_periods`, `triggered_periods`, `all_trigger_periods`, `primary_trigger_period`, or `triggered_period_details`
- HINT matched rows with non-empty formal periods or non-empty `triggered_period_details`
- `30m` in formal period arrays
- ordinary/FULL matched rows using `trigger_period=30m`
- FULL negative guard violations
- inconsistent 30m projection flags
- any N4 payload/write plan containing final `action_mark`

## Code Changes

- `src/ashare_v3/trigger/rule_v4_matcher.py`
- `src/ashare_v3/trigger/projection_matcher.py`
- `src/ashare_v3/trigger/projection_matcher_execute.py`
- `src/ashare_v3/trigger/v4_enforcement.py`
- `src/ashare_v3/trigger/v4_corrected_dry_run.py`
- `scripts/run_n4_20260605_v4_corrected_execute_once.py`
- `tests/test_n4_trigger_rule_v4_matcher.py`
- `tests/test_n4_v4_enforcement.py`
- `tests/test_trigger_projection_matcher.py`
- `tests/test_trigger_projection_matcher_execute.py`

## Validation

- `PYTHONPATH=src python3 -m unittest tests.test_n4_trigger_rule_v4_matcher tests.test_n4_v4_enforcement tests.test_trigger_projection_matcher tests.test_trigger_projection_matcher_execute`: PASS, 85 tests
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_n4*.py'`: PASS, 96 tests
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_trigger*.py'`: PASS, 128 tests
- `PYTHONPATH=src python3 scripts/check_n4_contract.py`: PASS
- `python3 -m compileall src/ashare_v3/trigger tests`: PASS
- `python3 -m json.tool docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_DRY_RUN_ALIGNMENT_REPORT.json >/dev/null`: PASS
- `git diff --check`: PASS

## Next Gate

Allowed next gate:

`N4_PROJECTION_MATCHER_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_REGENERATION_GATE`
