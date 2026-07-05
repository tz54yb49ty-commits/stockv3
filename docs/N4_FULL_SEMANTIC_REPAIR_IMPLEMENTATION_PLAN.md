# N4 FULL Semantic Repair Implementation Plan

Result: **IMPLEMENTATION_PLAN_PASS**

This gate does not implement the repair. It defines the implementation path for a later `N4_FULL_SEMANTIC_REPAIR_IMPLEMENTATION_GATE`.

Canonical worker plan: `docs/superpowers/plans/2026-06-09-n4-full-semantic-repair.md`

## Summary

Replace the current categorical `full_semantics_blocked` / `FULL forbidden` behavior with a strict whitelist:

```text
N2 explicit FULL context
+ D current_transition=volume_up / low_volume_down
+ D amount chain pass
-> N4 TriggerMatched
```

Legal FULL output remains ordinary runtime trigger output:

```text
signal_type=B_BUY/S_SELL
trigger_kind=trigger
trigger_period=D
triggered_periods=["D"]
all_trigger_periods=["D"]
primary_trigger_period=D
trigger_mark_candidate=normal
n5_entry_allowed=true
```

## Code Scope

- `src/ashare_v3/trigger/rule_v4_matcher.py`
- `src/ashare_v3/trigger/v4_enforcement.py`
- `src/ashare_v3/trigger/v4_corrected_dry_run.py`
- `src/ashare_v3/trigger/v4_corrected_execute_contract.py`
- `tests/test_n4_trigger_rule_v4_matcher.py`
- `tests/test_n4_v4_enforcement.py`
- `tests/test_n4_20260605_v4_corrected_dry_run.py`
- `tests/test_n4_20260605_v4_corrected_execute_contract.py`
- `tests/test_n4_trigger_rule_v4_execute.py`

## Validation Commands

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_n4_trigger_rule_v4_matcher.py \
  tests/test_n4_v4_enforcement.py \
  tests/test_n4_20260605_v4_corrected_dry_run.py \
  tests/test_n4_20260605_v4_corrected_execute_contract.py \
  tests/test_n4_trigger_rule_v4_execute.py

PYTHONPATH=src python3 scripts/check_n4_contract.py
python3 -m compileall src/ashare_v3/trigger tests
python3 -m json.tool docs/N4_FULL_SEMANTIC_REPAIR_CONTRACT.json >/dev/null
python3 -m json.tool docs/N4_FULL_SEMANTIC_REPAIR_DRY_RUN.json >/dev/null
python3 -m json.tool docs/N4_FULL_SEMANTIC_REPAIR_IMPLEMENTATION_PLAN.json >/dev/null
git diff --check
```

## Boundary

- No N4 execute in this gate.
- No DB write in this gate.
- No rollback in this gate.
- No N5/N6 in this gate.
- No outbox/inbox/checkpoint mutation.
- No worker.
