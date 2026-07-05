# N4 Formal Trigger Amount Unit / Baseline Alignment Final Closeout

Result: `CLOSEOUT_PASS`

Generated at: `2026-06-15T18:48:02+08:00`

## Summary

The N4 formal amount guard fix is closed out for the 20260615 impacted lineage.

The repaired rule is:

- ordinary `BUY/SELL/FULL` formal period triggers must use `current_amount_metric_source_kind=N3_standard_period_metric`;
- N2 trigger baseline and N3 current amount metric must carry compatible amount-unit proof;
- `realtime_daily_snapshot.amount` is retained only as `snapshot_amount_trace` and cannot be promoted into formal trigger amount proof.

This cuts off the polluted path where raw snapshot amount could be compared directly with N2 formal trigger baselines.

## Implementation Proof

- Implementation result: `ALIGNMENT_PASS`
- Report:
  - `docs/N4_FORMAL_TRIGGER_AMOUNT_UNIT_BASELINE_ALIGNMENT_REPORT.json`
  - `docs/N4_FORMAL_TRIGGER_AMOUNT_UNIT_BASELINE_ALIGNMENT_REPORT.md`
- Main files:
  - `src/ashare_v3/trigger/projection_matcher.py`
  - `src/ashare_v3/trigger/rule_v4_matcher.py`
  - `tests/test_trigger_projection_matcher.py`
  - `tests/test_n4_trigger_rule_v4_matcher.py`

## Polluted Lineage Rollback Proof

Scoped rollback was executed for the polluted 20260615 N4/N5/N6 lineage.

- Rollback result: `ROLLBACK_PASS`
- Rollback SQL: `sql/V3_20260615_formal_amount_guard_polluted_lineage_rollback.sql`
- Execute report:
  - `docs/N4_FORMAL_TRIGGER_AMOUNT_UNIT_BASELINE_20260615_POLLUTED_LINEAGE_ROLLBACK_EXECUTE_REPORT.json`
  - `docs/N4_FORMAL_TRIGGER_AMOUNT_UNIT_BASELINE_20260615_POLLUTED_LINEAGE_ROLLBACK_EXECUTE_REPORT.md`

Post-rollback live proof:

```text
old_n4_run=0
old_n4_trigger_match=0
old_n4_outbox=0
```

## Fixed N4 Replay Proof

New fixed N4 run:

```text
n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_amount_guard_fix_v1
```

Live result:

```text
TriggerMatched pending=30
TriggerPendingMarketData pending=4203
ordinary formal TriggerMatched=0
ordinary formal 30m contamination=0
```

The 30 matched rows are HINT 30m projection triggers. Ordinary `BUY/SELL/FULL` rows are no longer matched through snapshot amount fallback.

Artifacts:

- `docs/N4_FORMAL_AMOUNT_GUARD_20260615_N4_REPLAY_DRY_RUN.json`
- `docs/N4_FORMAL_AMOUNT_GUARD_20260615_N4_REPLAY_PREFLIGHT.json`
- `docs/N4_FORMAL_AMOUNT_GUARD_20260615_N4_REPLAY_EXECUTE_REPORT.json`
- `sql/N4_FORMAL_AMOUNT_GUARD_20260615_n4_replay_rollback.sql`

## N3 Metric Proof

N3 generated a scoped action-confirmation metric run for the fixed N4 matched events:

```text
action_confirmation_projection_metric_20260615_until_1000_after_n4_amount_guard_fix_v1
```

Rows:

```text
stock/index/board/total = 29/0/1/30
join coverage = 30/30
missing = 0
```

Artifacts:

- `docs/N3_20260615_ACTION_CONFIRMATION_METRIC_UNTIL_1000_AMOUNT_GUARD_FIX_PAYLOAD.json`
- `docs/N3_20260615_ACTION_CONFIRMATION_METRIC_UNTIL_1000_AMOUNT_GUARD_FIX_CONTRACT.json`
- `docs/N3_20260615_ACTION_CONFIRMATION_METRIC_UNTIL_1000_AMOUNT_GUARD_FIX_PREFLIGHT.json`
- `docs/N3_20260615_ACTION_CONFIRMATION_METRIC_UNTIL_1000_AMOUNT_GUARD_FIX_EXECUTE_REPORT.json`
- `sql/N3_20260615_action_confirmation_metric_until_1000_AMOUNT_GUARD_FIX_rollback.sql`

## N5 Replay Proof

New fixed N5 run:

```text
n5_action_bounded_20260615_after_n4_amount_guard_fix_until_1000_v1
```

Consumer:

```text
n5_action_bounded_consumer_20260615_after_n4_amount_guard_fix_until_1000_v1
```

Live result:

```text
metric join coverage = 30/30
ActionExecuted = 3
ActionBlocked = 27
ActionEligible = 0
ActionSkipped = 0
N5 outbox pending = 30
delivered/delivering = 0/0
```

Artifacts:

- `docs/N4_FORMAL_AMOUNT_GUARD_20260615_N5_REPLAY_BASELINE.json`
- `docs/N4_FORMAL_AMOUNT_GUARD_20260615_N5_REPLAY_EXECUTE_REPORT.json`
- `sql/N4_FORMAL_AMOUNT_GUARD_20260615_n5_replay_rollback.sql`

## N6 Projection Proof

New N6 projection run:

```text
v3_n6_user_projection_20260615_after_n5_amount_guard_fix_until_1000_v1
```

Live result:

```text
user_projection_run = 1
user_signal_projection = 3
user_signal_card = 3
user_notification_queue = 0
```

Only `ActionEligible/ActionExecuted` are projected to ordinary user messages, so the 27 `ActionBlocked` rows remain diagnostic/status-only.

Artifacts:

- `docs/N4_FORMAL_AMOUNT_GUARD_20260615_N6_PROJECTION_CONTRACT.json`
- `docs/N4_FORMAL_AMOUNT_GUARD_20260615_N6_PROJECTION_PREFLIGHT.json`
- `docs/N4_FORMAL_AMOUNT_GUARD_20260615_N6_PROJECTION_EXECUTE_REPORT.json`
- `sql/N4_FORMAL_AMOUNT_GUARD_20260615_n6_projection_rollback.sql`

## Boundary Proof

```text
N4 outbox status updated = false
N5 outbox status updated = false
scheduler/worker started = false
voice/mobile touched = false
sim/position/order/real_trade touched = false
old_system_touched = false
user_sim_order/user_sim_trade/user_sim_position = 0/0/0
```

## Validation

```text
JSON parse PASS
targeted N4 tests PASS
trigger test group PASS
N5/N6 targeted tests PASS
scripts/check_n4_contract.py PASS
compileall PASS
rollback static check PASS
git diff --check PASS
```

Completion marker:

```text
N4_FORMAL_TRIGGER_AMOUNT_UNIT_BASELINE_ALIGNMENT_COMPLETE
```

Next recommended gate:

```text
V3_REALTIME_ENGINE_REACTIVATION_FINAL_GATE_AFTER_FORMAL_AMOUNT_GUARD_CLOSEOUT
```
