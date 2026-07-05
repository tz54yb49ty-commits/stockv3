# V3 20260612 N4 Trigger Period Baseline Fixed Replay Runner Alignment

- result: `ALIGNMENT_PASS`
- layer_role: `N4_trigger`
- target_run_id: `v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1`
- database_written: `false`
- n4_execute_run: `false`
- rollback_executed: `false`
- n5_n6_entered: `false`
- worker_started: `false`

## Root Cause

The fixed replay runner still defaulted to the historical replay run id and did not expose explicit artifact paths. The action-confirmation metric replay path also promoted ordinary BUY/SELL metric evidence into formal N4 `TriggerMatched` output using `30m` as a formal trigger period, even when no explicit Y/Q/M/W/D period proof was present.

## Code Repair Summary

- `scripts/run_v3_20260612_n4_full_day_trigger_replay_once.py`
  - added explicit `--execute-run-id`
  - added explicit dry-run / contract / preflight / execute / rollback artifact path arguments
  - wrote refreshed fixed replay artifacts for the target run id
  - added strict summary guards for ordinary formal 30m contamination and known polluted sample proof
- `src/ashare_v3/trigger/action_confirmation_metric_matcher.py`
  - ordinary BUY/SELL requires explicit formal N4 period proof before `TriggerMatched`
  - ordinary missing formal proof becomes `TriggerPendingMarketData`
  - `30m` remains projection evidence only unless the condition is `BUY_HINT` / `SELL_HINT`
  - rollback SQL generation now hard-fails by run-id setting before DELETE and guards downstream refs

## Fixed Replay Artifact Proof

- dry-run: `DRY_RUN_PASS`
- contract: `CONTRACT_PASS`
- preflight: `PREFLIGHT_PASS`
- candidate_count: `118668`
- TriggerMatched: `1187`
- TriggerPendingMarketData: `28206`
- TriggerStateChanged: `89275`
- planned common_trigger_state: `4101`
- planned common_trigger_match: `1187`
- planned common_event_outbox: `118668`
- P0/P1/P2: `0/1/0`

## Decontamination Proof

- ordinary_formal_30m_contamination_count: `0`
- formal_period_arrays_contains_30m_count: `0`
- ordinary_formal_missing_proof_trigger_matched_count: `0`
- ordinary_formal_missing_proof_pending_count: `52607`
- known polluted sample candidate count: `29`
- known polluted sample TriggerMatched count: `0`
- known polluted sample formal-missing pending count: `14`

## HINT Compatibility Proof

- HINT 30m TriggerMatched count: `1187`
- HINT remains allowed to use `trigger_period=30m`
- HINT formal period arrays remain empty and are covered by existing trigger tests

## Rollback Proof

- rollback SQL: `sql/V3_20260612_n4_trigger_period_baseline_fixed_replay_rollback.sql`
- hard-fail before first DELETE/UPDATE: `true`
- guards delivered/delivering N4 outbox: `true`
- guards downstream N5/N6/user/sim/order/trade/position refs: `true`
- no CASCADE/DROP/TRUNCATE: `true`
- rollback executed: `false`

## Validation

- targeted N4 replay runner tests: `PASS`
- targeted action-confirmation matcher tests: `PASS`
- trigger test group: `142 tests PASS`
- `scripts/check_n4_contract.py`: `PASS`
- JSON parse: `PASS`
- rollback static check: `PASS`
- compileall: `PASS`

## Forbidden Scope Proof

- N4 execute: `false`
- database_written: `false`
- rollback executed: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- N5/N6 entered: `false`
- scheduler/worker started: `false`
- voice/mobile/sim/position/order/real_trade touched: `false`
- old system touched: `false`

## Next Prompt

Proceed to runtime_control final gate review:

```text
layer_role=runtime_control。

进入 V3_20260612_N4_TRIGGER_PERIOD_BASELINE_FIXED_REPLAY_FINAL_GATE_REVIEW。

目标：
只读复核 20260612 fixed N4 replay dry-run / contract / preflight / rollback artifacts，确认是否允许进入用户确认 execute gate。
```
