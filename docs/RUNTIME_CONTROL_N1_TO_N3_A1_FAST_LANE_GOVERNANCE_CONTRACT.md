# Runtime Control N1 to N3-A1 Fast Lane Governance Contract

Gate: `RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_GOVERNANCE_CONTRACT_GATE`

Result: `CONTRACT_PASS`

Layer role: `runtime_control`

Contract version: `v1`

This gate only creates governance contract artifacts. It does not execute N1/N2/N3 commands, write the database, execute rollback SQL, consume or update outbox/inbox/checkpoint, start workers, enter N3-B/N3-C/N4/N5/N6, pull realtime market data, touch delivery/push/voice/mobile, touch sim/position/PnL/real trade, generate proposal/order/trade, or touch the old system.

## 1. Fast Lane Goal

The Fast Lane compresses routine trading-day N1 -> N3-A1 work into five large gates:

```text
1. RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_READINESS_GATE
2. N1_INGESTION_FAST_LANE_BUNDLE_EXECUTE_GATE
3. N2_CONDITION_FAST_LANE_BUNDLE_EXECUTE_GATE
4. N3_MARKET_DATA_A1_FAST_LANE_BUNDLE_EXECUTE_GATE
5. RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_CLOSEOUT_GATE
```

It is only for routine trading days. Any abnormality must automatically `BLOCK` and expand into a scoped repair gate. The intent is to merge repetitive review, dry-run, preflight, post-check, and closeout paperwork without weakening layer-role isolation, rollback safety, P0 hard gates, or audit evidence.

## 2. Non-Negotiable Boundaries

- `runtime_control` does not execute N1/N2/N3 commands.
- N1/N2/N3 execute must switch to the matching `layer_role`.
- N1 bundle must not write N2 or N3.
- N2 bundle must not pull market data or write N3.
- N3-A1 bundle must not enter N3-B, N3-C, N4, N5, or N6.
- Every execute command still requires `--execute --user-confirmed`.
- Rollback SQL must exist and pass static guard.
- `P0 > 0` must `BLOCK`.
- Unexpected outbox/inbox/checkpoint delta must `BLOCK`.
- N4/N5/N6 refs nonzero must `BLOCK`.
- Any old-system touch attempt must `BLOCK`.

## 3. Gate Consolidation Rules

Allowed to merge:

- Readiness + dry-run + preflight review within the same layer gate.
- Multiple same-layer post-checks.
- Runtime-control closeout registration.

Not allowed to merge:

- Cross-layer execute.
- Rollback execute.
- Outbox consumption.
- Worker start.
- N3-B/C realtime pull.
- N4/N5/N6 execute.
- Sim or real trade.

## 4. Fast Lane Gate Design

### RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_READINESS_GATE

Layer role: `runtime_control`

Allowed writes:

- `docs/fastlane/<for_trade_date>/01_runtime_readiness.md`
- `docs/fastlane/<for_trade_date>/01_runtime_readiness.json`

Required artifacts:

- For-trade-date readiness report.
- Trade-calendar expectation.
- Source-date and previous-trade-date proof.
- Expected layer-role handoff commands.
- Rollback-path inventory.

Required validation:

- Target date is a routine trading day, or the gate blocks.
- No existing active/run conflict for planned bundle ids.
- N4/N5/N6 refs are zero for planned fresh run ids.
- Required rollback SQL paths exist or are planned for downstream layer gates.
- Forbidden-scope side effects are all false.

BLOCK conditions:

- Missing trade calendar.
- Current date / trade date freshness violation.
- Existing active/run conflict.
- Old-system touch attempt.
- Downstream refs nonzero for planned fresh run ids.
- Required handoff command cannot be resolved.

### N1_INGESTION_FAST_LANE_BUNDLE_EXECUTE_GATE

Layer role: `N1_ingestion`

Allowed writes:

- Trade-calendar patch only if required and preflight-approved.
- Official daily facts.
- Stock identity repair only if pre-authorized and scoped.
- Official no-trade manifest proof.
- Condition source activation rows.
- N1 quality/run/audit rows.
- `docs/fastlane/<for_trade_date>/02_n1_bundle_execute_report.md/json`

Forbidden:

- N2 condition execute.
- N3 subscription or preload.
- Trigger/action/user layers.
- Parquet unless separately authorized.

Required validation:

- Every executed sub-command includes `--execute --user-confirmed`.
- `P0=0` for every sub-step.
- Expected rows equal actual rows.
- Rollback SQL exists and hard-fails before destructive action.
- Outbox/inbox/checkpoint delta is expected or zero.
- N2/N3/N4/N5/N6 refs are zero before handoff.

### N2_CONDITION_FAST_LANE_BUNDLE_EXECUTE_GATE

Layer role: `N2_condition`

Allowed writes:

- `common_condition_run`
- `common_condition_quality_item`
- `stock/index/board_condition_basis`
- `stock/index/board_condition_pool`
- `stock/index/board_minute_target_scope`
- `stock/index/board_condition_display_basis`
- `docs/fastlane/<for_trade_date>/03_n2_bundle_execute_report.md/json`

Forbidden:

- N3 subscription.
- Market data pull.
- N4/N5/N6.

Required validation:

- N1 source versions are active and match readiness.
- Default policy hash matches expected value.
- `P0=0`.
- Expected rows equal actual rows.
- Rollback SQL exists and hard-fails before destructive action.
- No N3/N4/N5/N6 refs before handoff.

### N3_MARKET_DATA_A1_FAST_LANE_BUNDLE_EXECUTE_GATE

Layer role: `N3_market_data`

Allowed writes:

- `common_market_data_run`
- `common_market_data_quality_item`
- `common_market_data_subscription_candidate`
- `common_market_data_subscription`
- `common_market_data_pull_plan`
- `stock/index/board_previous_day_minute_preload_status`
- `stock/index/board_minute_bar_1m` for previous-day preload only
- `docs/fastlane/<for_trade_date>/04_n3_a1_bundle_execute_report.md/json`

Forbidden:

- B1 realtime snapshot.
- C1 today minute.
- B2 realtime projection.
- Action-confirmation metric.
- N4/N5/N6.
- Worker or outbox consumption.

Required validation:

- N2 run is `passed_active` and matches readiness.
- Subscription rows deduplicate N2 scope.
- A1 expected rows equal actual rows.
- `P0=0`.
- Rollback SQL exists and hard-fails before destructive action.
- Unexpected outbox/inbox/checkpoint delta is zero.
- N4/N5/N6 refs are zero before closeout.

### RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_CLOSEOUT_GATE

Layer role: `runtime_control`

Allowed writes:

- `docs/fastlane/<for_trade_date>/05_closeout_registration.md`
- `docs/fastlane/<for_trade_date>/05_closeout_registration.json`

Required artifacts:

- `01_runtime_readiness.md/json`
- `02_n1_bundle_execute_report.md/json`
- `03_n2_bundle_execute_report.md/json`
- `04_n3_a1_bundle_execute_report.md/json`
- Rollback registry summary.
- Lineage summary.

Required validation:

- All prior bundle reports are `passed`.
- All P0 counts are zero.
- Rollback paths are registered.
- Unexpected outbox/inbox/checkpoint deltas are zero.
- N4/N5/N6 refs are zero.
- Forbidden scope flags are all false.

## 5. Bundle Artifact Schema

Suggested directory:

```text
docs/fastlane/<for_trade_date>/
```

Files:

```text
01_runtime_readiness.md
01_runtime_readiness.json
02_n1_bundle_execute_report.md
02_n1_bundle_execute_report.json
03_n2_bundle_execute_report.md
03_n2_bundle_execute_report.json
04_n3_a1_bundle_execute_report.md
04_n3_a1_bundle_execute_report.json
05_closeout_registration.md
05_closeout_registration.json
```

Minimum JSON fields:

```text
gate
result
layer_role
for_trade_date
source_trade_date
run_ids
expected_rows
actual_rows
p0_p1_p2
rollback_paths
outbox_inbox_checkpoint_delta
downstream_refs
forbidden_scope
validation
```

## 6. N1 Bundle Scope

Allowed:

- Trade calendar check/patch if required.
- Official daily ingestion.
- Stock identity repair only if pre-authorized and scoped.
- Official no-trade manifest validation.
- Condition source activation.
- N1 post-review summary.

Forbidden:

- N2 condition execute.
- N3 subscription/preload.
- Trigger/action/user.
- Parquet unless separately authorized.

## 7. N2 Bundle Scope

Allowed:

- Default policy hash proof.
- Dry-run/preflight.
- Execute/overwrite if needed.
- Post-review.

Forbidden:

- N3 subscription.
- Market data pull.
- N4/N5/N6.

## 8. N3-A1 Bundle Scope

Allowed:

- Market-data subscription control-row registration.
- Previous-day minute preload.
- Post-review.

Forbidden:

- B1 realtime snapshot.
- C1 today minute.
- B2 projection.
- Action-confirmation metric.
- N4/N5/N6.
- Worker/outbox consumption.

## 9. Global BLOCK Conditions

- Missing trade calendar.
- Identity coverage gap.
- No-trade manifest mismatch.
- Source row mismatch.
- Policy hash mismatch.
- Expected rows not equal to actual rows.
- Rollback SQL missing or unsafe.
- `P0 > 0`.
- Unexpected outbox/inbox/checkpoint delta.
- Downstream refs nonzero.
- Existing active/run conflict.
- Current date / trade date freshness violation.
- Old-system touch attempt.

## 10. Runner Wrapper Requirements

Future wrappers may be implemented in a later gate, but this gate does not implement them:

```text
scripts/run_n1_fastlane_bundle_once.py
scripts/run_n2_fastlane_bundle_once.py
scripts/run_n3_a1_fastlane_bundle_once.py
```

Wrapper requirements:

- Only orchestrate existing same-layer guarded runners.
- Do not bypass child runner `--execute --user-confirmed` guards.
- Every execute-mode child command must include `--execute --user-confirmed`.
- Stop immediately on sub-step failure.
- Emit a bundle report.
- Preserve original report paths.
- Do not swallow original failures.
- Do not cross `layer_role`.
- Do not consume outbox or start workers.
- Do not execute rollback.

## 11. Forbidden Scope Proof

```text
n1_n2_n3_commands_executed=false
database_written=false
rollback_sql_executed=false
outbox_inbox_checkpoint_consumed_or_updated=false
worker_started=false
n3_b_or_n3_c_entered=false
n4_n5_n6_entered=false
realtime_market_data_pulled=false
delivery_push_voice_mobile_touched=false
sim_position_pnl_real_trade_touched=false
proposal_order_trade_touched=false
old_system_touched=false
```

## 12. Validation

```text
JSON parse=PASS
contract consistency=PASS
forbidden scope proof=PASS
git diff --check=PASS
```

## Next Gate Recommendation

```text
RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_IMPLEMENTATION_PLAN_GATE
```
