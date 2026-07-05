# N4 Unified Trigger Signal Output HINT Event Time Alignment Report

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

## Root Cause

The unified output alignment required every N4 output payload path to expose `event_time`.

For HINT `TriggerMatched` rows, `projection_matcher.build_evaluation()` already carried:

- `trigger_time`
- `projection_trace.trigger_time`
- N3 projection/source confirmation trace

But the dry-run plan itself did not expose a top-level `event_time`. The execute plan then copied the accepted N3 source event into `source_event_time`, but also did not materialize a top-level `event_time` in `trigger_output_plan`.

As a result, the retry dry-run/preflight could pass semantic scans, while the final gate scanner found 122 HINT `TriggerMatched` rows missing the required unified `event_time` field.

## Code Changes

- `src/ashare_v3/trigger/projection_matcher.py`
  - HINT matched dry-run evaluations now set top-level `event_time` from the N3 projection confirmed time.
- `src/ashare_v3/trigger/projection_matcher_execute.py`
  - Execute `trigger_output_plan` now materializes top-level `event_time`, with priority:
    1. accepted N3 outbox `event_time`
    2. dry-run evaluation `event_time`
    3. dry-run evaluation `trigger_time`
- `src/ashare_v3/trigger/v4_enforcement.py`
  - `event_time` is now a required `TriggerMatched` field before any write.
- `tests/test_trigger_projection_matcher.py`
  - Added HINT dry-run proof that matched rows carry `event_time` equal to projection trace trigger time.
- `tests/test_trigger_projection_matcher_execute.py`
  - Added execute plan and payload proof that HINT rows carry `event_time` from the accepted N3 source event.
- `tests/test_n4_v4_enforcement.py`
  - Added missing `event_time` enforcement regression.

## HINT Event Time Proof

HINT `TriggerMatched` rows now carry:

- `trigger_time`: N3 projection confirmed time
- `event_time`: same projection confirmed time in dry-run plans
- execute `event_time`: accepted N3 `MarketSnapshotUpdated` outbox event time
- `projection_trace.trigger_time`: retained for audit

No N5/N6 field is used to fill `event_time`.

## Unified Required Field Proof

The repaired path keeps all previous unified semantics:

- runtime `signal_type` remains only `B_BUY` / `S_SELL`
- `BUY_HINT` / `SELL_HINT` remain `condition_signal_type`, not runtime `signal_type`
- HINT `trigger_period=30m` remains legal
- HINT formal fields remain empty/null:
  - `triggered_periods=[]`
  - `all_trigger_periods=[]`
  - `primary_trigger_period=null`
  - `triggered_period_details=[]`
- `projection_30m_required=true`
- `projection_30m_flag=true`
- `projection_period=30m`
- `projection_30m_type=volume_up/shrink_down`
- N4 payload still does not emit `action_mark`

## Validation

- `PYTHONPATH=src python3 -m unittest tests.test_n4_v4_enforcement tests.test_trigger_projection_matcher tests.test_trigger_projection_matcher_execute`: PASS, 72 tests
- `PYTHONPATH=src python3 -m unittest tests.test_n4_trigger_rule_v4_matcher tests.test_n4_v4_enforcement tests.test_trigger_projection_matcher tests.test_trigger_projection_matcher_execute`: PASS, 86 tests
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_n4*.py'`: PASS, 97 tests
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_trigger*.py'`: PASS, 128 tests
- `PYTHONPATH=src python3 scripts/check_n4_contract.py`: PASS
- `python3 -m compileall src/ashare_v3/trigger tests`: PASS
- `python3 -m json.tool docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_HINT_EVENT_TIME_ALIGNMENT_REPORT.json >/dev/null`: PASS
- `git diff --check`: PASS

## Next Gate

Allowed next gate after validation:

`N4_PROJECTION_MATCHER_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_REGENERATION_GATE`
