# N4/N5 Trigger Period 与 Trigger Baseline 口径修复 Post Review

Result: `POST_REVIEW_PASS`

Generated at: `2026-06-15T07:50:48Z`

## Implementation Proof

依据 [implementation report](/Users/chuanfuchen/Documents/A股监控系统v3/docs/N4_N5_TRIGGER_PERIOD_BASELINE_ALIGNMENT_IMPLEMENTATION_REPORT.md) 和 JSON artifact 复核，implementation result 为 `IMPLEMENTATION_PASS`，报告 JSON parse PASS。

## N5 Formal Passthrough Proof

N5 已停止从以下字段反推已触发 formal periods：

- `condition_key`
- `original_condition_key`
- `required_periods`
- `period_trigger_baseline_trace.traced_periods`

[canonicalize_n5_trigger_period_passthrough](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/action/execute.py:2520) 只透传 N4 payload 已证明的：

- `triggered_periods`
- `all_trigger_periods`
- `primary_trigger_period`

旧 helper `formal_periods_from_condition_key` / `formal_periods_from_trace` 仍存在，但不再被 N5 passthrough 用来伪造 formal trigger proof。

## N5 Fail-Closed Proof

[evaluate_n4_formal_trigger_period_proof](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/action/dry_run.py:461) 已登记：

- 普通 formal `TriggerMatched`
- `trigger_period=30m`
- formal `triggered_periods=[]`

会 fail-closed 为：

```text
ActionBlocked
blocked_reason=n4_formal_trigger_period_missing
```

`BUY_HINT / SELL_HINT` 保持例外，因为它们本身是 N2 hint 条件 + N4 30m projection 确认，不要求 M/W/D formal periods。

## N4 Trigger Baseline Proof

[rule_v4_matcher._evaluate_period](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/trigger/rule_v4_matcher.py:433) 已强制读取：

- `trigger_previous_entity_high`
- `trigger_previous_entity_low`
- `trigger_previous_amount_baseline`

缺 `trigger_previous_*` 时返回 `TriggerPendingMarketData` / quality blocker，不 fallback 到 legacy `previous_*` 或 classification 字段。

## Amount Unit Proof

[rule_v4_matcher._amount_unit_status](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/trigger/rule_v4_matcher.py:703) 已登记金额单位硬门：

- N2 trigger baseline amount unit 和 N3 current amount metric unit 必须同时声明且一致。
- 单位不一致：`trigger_amount_unit_mismatch`
- 缺单位证明：`trigger_amount_unit_not_proven`

## Historical Pollution Audit Proof

已登记只读历史审计：

- `20260612/20260615` N4 `TriggerMatched` total: `82395`
- 普通 formal 条件 `trigger_period=30m` 且 formal periods 为空: `71263`
- linked N5 fabricated formal periods: `23845`
- `trigger_match_id=253831`: historical polluted fact

本 gate 未修改历史事实。后续必须通过 scoped replay / supersession / rollback gate 处理 UI 或用户消息里的旧错误展示。

## Validation Summary

- focused N4/N5 tests: PASS, `142 OK`
- trigger test group: PASS, `140 OK`
- `compileall`: PASS
- `scripts/check_n4_contract.py`: PASS, `finding_count=0`
- implementation report JSON parse: PASS
- scoped `git diff --check`: PASS

## Forbidden Scope Proof

- 未执行 N4/N5 runner
- 未写数据库
- 未执行 rollback
- 未消费/update outbox/inbox/checkpoint
- 未启动 scheduler/worker
- 未进入 N6
- 未触碰 voice/mobile/sim/position/order/real trade
- 未读取/修改旧系统

## Decision

允许登记：`POST_REVIEW_PASS`

允许进入：`N4_N5_TRIGGER_PERIOD_BASELINE_SCOPED_REPLAY_SUPERSESSION_PLANNING_GATE`

## Next Prompt

```text
layer_role=runtime_control。

进入 N4_N5_TRIGGER_PERIOD_BASELINE_SCOPED_REPLAY_SUPERSESSION_PLANNING_GATE。

目标：在 N4/N5 Trigger Period 与 Trigger Baseline 口径修复已 POST_REVIEW_PASS 后，只读制定 20260612/20260615 历史污染事实的 scoped replay / supersession 计划。确认哪些旧 N4/N5/N6 run 需要保留为 historical polluted evidence，哪些需要新 run_id 重放，是否需要 scoped rollback 以避免 UI 展示旧错误消息。

要求：不执行 N4/N5/N6 runner，不写数据库，不执行 rollback，不消费/update outbox/inbox/checkpoint，不启动 scheduler/worker，不触碰 voice/mobile/sim/position/order/real trade，不读取/修改旧系统。

请基于 implementation/post-review audit 复核：N4 ordinary formal 30m marker empty formal periods=71263，linked N5 fabricated formal periods=23845，trigger_match_id=253831 属于 historical polluted fact。输出 scoped replay source scope、supersession policy、rollback need decision、N6/UI impact、next execute gate sequence。
```
