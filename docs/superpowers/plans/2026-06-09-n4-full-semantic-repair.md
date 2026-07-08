# N4 FULL Semantic Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `BUY:FULL / SELL:FULL` legal N4 `TriggerMatched` outputs when N2 FULL context is explicit and D transition plus amount-chain evidence passes.

**Architecture:** Keep FULL discovery in N2 and only let N4 evaluate the localized FULL context. Replace the current categorical FULL block with a strict D-only whitelist in matcher and enforcement. Preserve ordinary BUY/SELL, HINT 30m, N5, and N6 semantics.

**Tech Stack:** Python 3.11, unittest, PostgreSQL read-only dry-run inputs, existing `ashare_v3.trigger` modules.

---

### Task 1: Add Matcher Red Tests

**Files:**
- Modify: `tests/test_n4_trigger_rule_v4_matcher.py`

- [ ] **Step 1: Replace the old FULL blocked test with legal BUY:FULL / SELL:FULL tests**

Add tests equivalent to:

```python
def test_buy_full_matches_only_on_d_volume_up_and_amount_chain_pass(self):
    plan = evaluate_v4_plan(
        _context_row(
            "BUY:FULL",
            period_trigger_baseline_json={
                "periods": {
                    "D": {
                        "period_baseline_ready": True,
                        "previous_transition": "flat",
                        "previous_entity_high": "10",
                        "previous_entity_low": "8",
                        "previous_amount_baseline": "100",
                    }
                }
            },
        ),
        _projection(
            current_price_or_close="10.5",
            current_amount_metric="120",
            trigger_amount_chain_pass={"D": True},
            projection_30m_type="none",
        ),
        v4_run_id="trigger_rule_v4_dry_run_test",
    )
    self.assertEqual(plan["outcome_classification"], "matched")
    self.assertEqual(plan["output_event_type"], "TriggerMatched")
    self.assertEqual(plan["signal_type"], "B_BUY")
    self.assertEqual(plan["trigger_kind"], "trigger")
    self.assertEqual(plan["trigger_period"], "D")
    self.assertEqual(plan["triggered_periods"], ["D"])
    self.assertEqual(plan["all_trigger_periods"], ["D"])
    self.assertEqual(plan["primary_trigger_period"], "D")
    self.assertEqual(plan["trigger_mark_candidate"], "normal")
    self.assertTrue(plan["n5_entry_allowed"])
```

Add the symmetric `SELL:FULL` case with `current_price_or_close` below `previous_entity_low`, `current_amount_metric` below baseline, and expected `S_SELL`.

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests/test_n4_trigger_rule_v4_matcher.py
```

Expected before implementation: failure because FULL still returns `quality_blocked/full_semantics_blocked`.

### Task 2: Implement FULL D Evaluator

**Files:**
- Modify: `src/ashare_v3/trigger/rule_v4_matcher.py`

- [ ] **Step 1: Replace the FULL branch**

Replace the early `if condition_family == "full": return _finalize_plan(... full_semantics_blocked ...)` branch with:

```python
if condition_family == "full":
    return _evaluate_full(base_plan, direction, period_baselines, projection)
```

- [ ] **Step 2: Add `_evaluate_full`**

Add:

```python
def _evaluate_full(
    base_plan: dict[str, Any],
    direction: str,
    period_baselines: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    if not projection:
        return _finalize_plan(
            base_plan,
            outcome="pending_market_data",
            triggered_periods=[],
            details=[_period_pending_detail("D", period_baselines, "missing_projection_enrichment")],
            pending_reasons=["missing_projection_enrichment"],
        )

    quality_reason = _projection_quality_reason(projection)
    if quality_reason:
        return _finalize_plan(
            base_plan,
            outcome="quality_blocked",
            triggered_periods=[],
            details=[_period_quality_detail("D", period_baselines, quality_reason)],
            blocked_reason=quality_reason,
            quality_reasons=[quality_reason],
        )

    target_transition = "volume_up" if direction == "buy" else "low_volume_down"
    detail = _evaluate_period("D", direction, target_transition, period_baselines, projection)
    if detail["classification"] == "triggered":
        return _finalize_plan(base_plan, outcome="matched", triggered_periods=["D"], details=[detail])
    if detail["classification"] == "pending":
        return _finalize_plan(
            base_plan,
            outcome="pending_market_data",
            triggered_periods=[],
            details=[detail],
            pending_reasons=[detail["reason"]],
        )
    if detail["classification"] == "quality_blocked":
        return _finalize_plan(
            base_plan,
            outcome="quality_blocked",
            triggered_periods=[],
            details=[detail],
            blocked_reason=detail["reason"],
            quality_reasons=[detail["reason"]],
        )
    return _finalize_plan(base_plan, outcome="no_op", triggered_periods=[], details=[detail])
```

- [ ] **Step 3: Run matcher tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests/test_n4_trigger_rule_v4_matcher.py
```

Expected: matcher tests pass after updating old FULL-block expectations.

### Task 3: Replace Enforcement FULL Forbid With Whitelist

**Files:**
- Modify: `src/ashare_v3/trigger/v4_enforcement.py`
- Modify: `tests/test_n4_v4_enforcement.py`

- [ ] **Step 1: Add legal FULL enforcement tests**

Update the old `test_full_condition_key_blocks_trigger_matched` to prove legal `BUY:FULL` passes when:

```python
plan["condition_key"] = "BUY:FULL"
plan["original_condition_key"] = "BUY:FULL"
plan["trigger_kind"] = "trigger"
plan["signal_type"] = "B_BUY"
plan["trigger_period"] = "D"
plan["triggered_periods"] = ["D"]
plan["all_trigger_periods"] = ["D"]
plan["primary_trigger_period"] = "D"
plan["trigger_mark_candidate"] = "normal"
plan["projection_30m_flag"] = False
plan["projection_30m_type"] = "none"
```

Also add negative tests for FULL with period `30m`, FULL with trigger_kind `hint`, FULL with `trigger_mark_candidate=30m_volume`, and FULL missing `trigger_price`.

- [ ] **Step 2: Implement whitelist helper**

In `collect_v4_trigger_matched_plan_violations`, remove the unconditional:

```python
if plan.get("condition_key") in FULL_CONDITION_KEYS or plan.get("original_condition_key") in FULL_CONDITION_KEYS:
    violations.append("full_condition_matched_forbidden")
```

Replace with a helper call:

```python
violations.extend(_full_trigger_violations(plan))
```

Add:

```python
def _full_trigger_violations(plan: Mapping[str, Any]) -> list[str]:
    condition_key = str(plan.get("condition_key") or "")
    original = str(plan.get("original_condition_key") or condition_key)
    if condition_key not in FULL_CONDITION_KEYS and original not in FULL_CONDITION_KEYS:
        return []
    violations: list[str] = []
    expected_signal = "B_BUY" if condition_key == "BUY:FULL" or original == "BUY:FULL" else "S_SELL"
    if plan.get("trigger_kind") != "trigger":
        violations.append("full_trigger_kind_must_be_trigger")
    if plan.get("signal_type") != expected_signal:
        violations.append("full_runtime_signal_type_invalid")
    if _period_text(plan.get("trigger_period")) != "D":
        violations.append("full_trigger_period_must_be_D")
    if _period_text(plan.get("primary_trigger_period")) != "D":
        violations.append("full_primary_trigger_period_must_be_D")
    if _period_values(plan.get("triggered_periods")) != ["D"]:
        violations.append("full_triggered_periods_must_be_D")
    if _period_values(plan.get("all_trigger_periods")) != ["D"]:
        violations.append("full_all_trigger_periods_must_be_D")
    if str(plan.get("trigger_mark_candidate") or "") != "normal":
        violations.append("full_trigger_mark_candidate_must_be_normal")
    if plan.get("projection_30m_flag") not in (False, None):
        violations.append("full_projection_30m_flag_must_be_false")
    if str(plan.get("projection_30m_type") or "none") != "none":
        violations.append("full_projection_30m_type_must_be_none")
    return violations
```

- [ ] **Step 3: Run enforcement tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests/test_n4_v4_enforcement.py
```

Expected: pass.

### Task 4: Update Corrected Dry-Run And Execute Contract Artifacts

**Files:**
- Modify: `src/ashare_v3/trigger/v4_corrected_dry_run.py`
- Modify: `src/ashare_v3/trigger/v4_corrected_execute_contract.py`
- Modify: `tests/test_n4_20260605_v4_corrected_dry_run.py`
- Modify: `tests/test_n4_20260605_v4_corrected_execute_contract.py`

- [ ] **Step 1: Replace reason labels**

Remove `full_condition_matched_forbidden -> FULL forbidden` as a normal expected blocker. Add labels for new FULL violations such as `FULL invalid period`, `FULL invalid mark`, and `FULL missing N2 context` only when they occur.

- [ ] **Step 2: Replace P0 guard name**

Replace `FULL_forbidden_by_default` with:

```python
"full_semantic_contract_guard"
```

- [ ] **Step 3: Update tests**

Expected contract fields:

```python
self.assertIn("full_semantic_contract_guard", contract["p0_guards"])
self.assertNotIn("FULL_forbidden_by_default", contract["p0_guards"])
```

### Task 5: Update Execute Write-Plan Tests

**Files:**
- Modify: `tests/test_n4_trigger_rule_v4_execute.py`

- [ ] **Step 1: Add valid FULL write-plan test**

Create a plan with:

```python
_plan("matched", condition_key="BUY:FULL", n5_entry_allowed=True, trigger_live=True)
```

Set `trigger_period="D"`, `triggered_periods=["D"]`, `all_trigger_periods=["D"]`, `primary_trigger_period="D"`, and assert write counts include it as `TriggerMatched`.

- [ ] **Step 2: Keep invalid FULL suppressed**

Add a negative FULL plan with invalid `trigger_period="30m"` and assert it is counted as blocked by enforcement before write.

### Task 6: Final Verification

**Files:**
- No edits unless tests reveal a narrow missing fixture.

- [ ] **Step 1: Run targeted N4 tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests/test_n4_trigger_rule_v4_matcher.py \
  tests/test_n4_v4_enforcement.py \
  tests/test_n4_20260605_v4_corrected_dry_run.py \
  tests/test_n4_20260605_v4_corrected_execute_contract.py \
  tests/test_n4_trigger_rule_v4_execute.py
```

- [ ] **Step 2: Run N4 contract checker**

```bash
PYTHONPATH=src python3 scripts/check_n4_contract.py
```

- [ ] **Step 3: Compile and static checks**

```bash
python3 -m compileall src/ashare_v3/trigger tests
python3 -m json.tool docs/N4_FULL_SEMANTIC_REPAIR_CONTRACT.json >/dev/null
python3 -m json.tool docs/N4_FULL_SEMANTIC_REPAIR_DRY_RUN.json >/dev/null
python3 -m json.tool docs/N4_FULL_SEMANTIC_REPAIR_IMPLEMENTATION_PLAN.json >/dev/null
git diff --check
```

Expected: all pass.

### Task 7: Implementation Report

**Files:**
- Create: `docs/N4_FULL_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.md`
- Create: `docs/N4_FULL_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.json`

- [ ] **Step 1: Record implementation proof**

The report must include:

```text
result=IMPLEMENTATION_PASS
BUY:FULL legal D TriggerMatched test PASS
SELL:FULL legal D TriggerMatched test PASS
invalid FULL period/mark/kind BLOCK
ordinary BUY/SELL unchanged
HINT 30m unchanged
no N4 execute
no DB write
no outbox/inbox/checkpoint mutation
no N5/N6
```

- [ ] **Step 2: Validate report JSON**

```bash
python3 -m json.tool docs/N4_FULL_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.json >/dev/null
```

Expected: pass.
