# N4/N5 Trigger Period Baseline Scoped Replay / Supersession Plan

Result: `POLICY_PASS`

Generated at: `2026-06-15T07:57:28Z`

## Post-Review Proof

N4/N5 Trigger Period 与 Trigger Baseline 口径修复已登记为 `POST_REVIEW_PASS`：

- [implementation report](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N4_N5_TRIGGER_PERIOD_BASELINE_ALIGNMENT_IMPLEMENTATION_REPORT.md)
- [post-review report](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N4_N5_TRIGGER_PERIOD_BASELINE_ALIGNMENT_POST_REVIEW.md)

本 planning gate 只读复核 lineage，不执行 N4/N5/N6 runner，不写数据库，不执行 rollback。

## Historical Pollution Scope Proof

只读审计 `20260612 / 20260615`：

- N4 `TriggerMatched` total: `82395`
- 普通 formal 条件中 `trigger_period=30m` 且 formal periods 为空: `71263`
- linked N5 fabricated formal periods: `23845`
- `trigger_match_id=253831`: historical polluted fact

污染全部命中 `20260612`。当前 `20260615` lineage 未命中这类 bug scope。

N4 polluted rows by run:

- `v3_n4_trigger_replay_20260612_after_n3_full_day_metric_v1`: `23068`
- `v3_n4_trigger_replay_20260612_after_n3_full_day_metric_mark_only_fix_v2`: `24095`
- `v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3`: `24095`
- `v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`: `5`

N5 polluted rows by run:

- `v3_n5_action_replay_20260612_after_n4_state_machine_v3`: `23840`
- `v3_n5_hint_basis_aligned_replay_20260612_from_n4_action_confirmation_metric_after_hint_basis_fix_v1`: `5`

## Active Lineage Impact Proof

Stale N5 outbox is still pending:

- `v3_n5_action_replay_20260612_after_n4_state_machine_v3`
  - `ActionExecuted pending=24116`
  - `ActionBlocked pending=911`
- `v3_n5_hint_basis_aligned_replay_20260612_from_n4_action_confirmation_metric_after_hint_basis_fix_v1`
  - `ActionExecuted pending=5`

N6/user projection refs:

- By stale N5 run: `0`
- By stale N5 event id: `0`

N4 source refs:

- `v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3` has N5 inbox refs:
  - consumer `v3_n5_action_replay_20260612_state_machine_consumer_v3`
  - `TriggerMatched processed=25282`

普通用户消息 UI source boundary:

- `/n6/app/messages` and `/n6/app/signals` use N6 projection/card/run sources.
- [app_v2_message_dashboard_source_policy](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/web/n6_app_v1.py:731) forbids N4/N5 raw fact bypass and `common_event_outbox`.
- Therefore ordinary user message pages should not show these polluted N5 rows unless a future N6 projection is run from stale N5.
- Raw/admin N5 pages may still show stale `common_action_event` / N5 outbox until scoped rollback or supersession.

## Replay vs Rollback Decision

Decision: use new run_id replay/supersession as the canonical repair path. Do not overwrite historical facts.

Recommended immediate cleanup:

- Roll back stale N5 runs first, because:
  - stale N5 outbox is pending only;
  - no delivered/delivering evidence was observed;
  - N6/user projection refs are `0`;
  - this prevents raw/admin views or accidental future N6 projection from exposing fabricated periods.

N6 rollback is not required now because N6 refs are `0`.

Do not directly rollback N4 in this planning step:

- N4 polluted runs are historical evidence.
- At least one N4 run has N5 inbox/checkpoint refs.
- Keep N4 as historical/superseded until stale N5 rollback and repaired replay are complete.
- Any N4 rollback must be a later explicit scoped gate.

## N4 Replay Scope

Recommended new N4 run:

```text
v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1
```

Scope:

- Full `20260612` N3 action-confirmation metric/time-series replay scope.
- Do not replay only polluted rows, because N4 state-machine transitions depend on complete ordered trigger state.

Required behavior:

- Use repaired `trigger_previous_entity_high/low` and `trigger_previous_amount_baseline`.
- Require N2 trigger baseline amount unit and N3 current amount unit proof.
- Do not emit ordinary formal `TriggerMatched` from `30m_volume / 30m_shrink` alone.
- `BUY_HINT / SELL_HINT` may still emit legal 30m projection `TriggerMatched`.
- Emit `TriggerPendingMarketData` or no-op when formal proof is missing.

Acceptance:

- ordinary formal 30m marker empty formal periods = `0`
- `trigger_match_id=253831` equivalent source no longer produces fabricated formal proof
- N4 event types remain `TriggerMatched / TriggerPendingMarketData / TriggerStateChanged`

`20260615` does not need replay for this specific bug unless a new audit finds bad rows.

## N5 Replay Scope

Recommended new N5 run:

```text
v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1
```

Scope:

- Consume only repaired N4 run `v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1`.

Required behavior:

- Only `TriggerMatched` starts action confirmation.
- N5 must not infer `triggered_periods / all_trigger_periods / primary_trigger_period` from `condition_key`, `original_condition_key`, `required_periods`, or trace.
- Ordinary formal 30m marker without formal N4 proof becomes `ActionBlocked(n4_formal_trigger_period_missing)`.
- `BUY_HINT / SELL_HINT` 30m projection remains legal.
- Final `action_mark` remains N5-owned from N3 action-confirmation metric.

Acceptance:

- linked fabricated formal periods = `0`
- `ActionExecuted` payload formal periods equal repaired N4 formal proof
- no N5 output from `TriggerPendingMarketData / TriggerStateChanged`
- canonical output events only: `ActionEligible / ActionBlocked / ActionExecuted / ActionSkipped`

## N6 / UI Impact

Current ordinary user-message pollution: `false`, because stale N5 has no N6 projection/card/queue refs.

Raw/admin N5 pollution: `true`, because stale `common_action_event` and N5 outbox rows still exist.

Recommended N6 projection after repaired N5:

```text
v3_n6_user_projection_20260612_after_n5_trigger_period_baseline_fix_v1
```

Source:

```text
v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1
```

Policy:

- ordinary user messages project only repaired `ActionEligible / ActionExecuted`;
- `ActionBlocked / ActionSkipped` stay diagnostic/status-monitor only.

## Recommended Gate Sequence

1. `V3_20260612_STALE_N5_TRIGGER_PERIOD_FABRICATION_ROLLBACK_CONTRACT_PREFLIGHT_GATE`
   - layer: `N5_action`
   - generate rollback artifacts for stale N5 runs only.

2. `V3_20260612_STALE_N5_TRIGGER_PERIOD_FABRICATION_ROLLBACK_EXECUTE_FINAL_GATE_REVIEW`
   - layer: `runtime_control`
   - review rollback safety: pending only, no N6 refs, N4 preserved.

3. `V3_20260612_N4_TRIGGER_PERIOD_BASELINE_FIXED_REPLAY_CONTRACT_PREFLIGHT_GATE`
   - layer: `N4_trigger`
   - generate repaired N4 replay artifacts.

4. `V3_20260612_N4_TRIGGER_PERIOD_BASELINE_FIXED_REPLAY_EXECUTE_FINAL_GATE_REVIEW`
   - layer: `runtime_control`
   - review N4 replay execute readiness.

5. `V3_20260612_N5_REPLAY_AFTER_N4_TRIGGER_PERIOD_BASELINE_FIX_CONTRACT_PREFLIGHT_GATE`
   - layer: `N5_action`
   - generate repaired N5 replay artifacts.

6. `V3_20260612_N5_REPLAY_AFTER_N4_TRIGGER_PERIOD_BASELINE_FIX_EXECUTE_FINAL_GATE_REVIEW`
   - layer: `runtime_control`
   - review N5 replay execute readiness.

7. `V3_20260612_N6_USER_PROJECTION_AFTER_TRIGGER_PERIOD_BASELINE_FIX_CONTRACT_PREFLIGHT_GATE`
   - layer: `N6_user`
   - generate N6 projection artifacts from repaired N5 output.

8. `V3_20260612_TRIGGER_PERIOD_BASELINE_FIX_CLOSEOUT_GATE`
   - layer: `runtime_control`
   - register stale runs as historical/superseded and repaired lineage as active display lineage.

## Forbidden Scope Proof

- 未执行 N4/N5/N6 runner
- 未写数据库
- 未执行 rollback
- 未消费/update outbox/inbox/checkpoint
- 未启动 scheduler/worker
- 未触碰 voice/mobile/sim/position/order/real trade
- 未读取/修改旧系统

## Next Prompt

```text
layer_role=N5_action。

进入 V3_20260612_STALE_N5_TRIGGER_PERIOD_FABRICATION_ROLLBACK_CONTRACT_PREFLIGHT_GATE。

目标：为 20260612 stale N5 trigger-period fabrication runs 生成 scoped rollback dry-run/contract/preflight/rollback SQL。目标 stale runs：v3_n5_action_replay_20260612_after_n4_state_machine_v3 与 v3_n5_hint_basis_aligned_replay_20260612_from_n4_action_confirmation_metric_after_hint_basis_fix_v1。只允许规划 rollback artifacts，不执行 rollback、不写 DB、不消费/update outbox/inbox/checkpoint、不进入 N4/N6/voice/mobile/sim/position/order/real trade、不读取/修改旧系统。

请复核：N5 outbox pending only、delivered/delivering=0、N6/user refs=0、N4 source run preserved、N5 inbox/checkpoint scope、rollback SQL hard-fail before DELETE/UPDATE、no DROP/TRUNCATE/CASCADE。输出 CONTRACT_PREFLIGHT_PASS / BLOCKED、rollback scope、safety proof、next runtime_control final gate prompt。
```
