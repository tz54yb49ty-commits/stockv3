# N4/N5 Trigger Period 与 Trigger Baseline 口径修复报告

Result: `IMPLEMENTATION_PASS`

Generated at: `2026-06-15T07:40:12Z`

## 结论

本轮确认并修复了两条叠加 bug：

- N5 不再从 `condition_key`、`original_condition_key`、`required_periods` 或 trace 反推 `triggered_periods`。N5 只能透传 N4 已证明的 formal trigger fields。
- N4 v4 formal matcher 不再使用 `previous_entity_high/low`、`previous_amount_baseline` 作为正式触发阈值，改为强制读取 `trigger_previous_entity_high/low`、`trigger_previous_amount_baseline`。
- N4 金额比较新增单位证明硬门：N2 trigger baseline 与 N3 当前金额 metric 的单位必须同时声明且一致；缺单位证明或单位不一致都不得 matched。

## 实现证明

- [src/ashare_v3/action/execute.py](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/action/execute.py:2520)
  - `canonicalize_n5_trigger_period_passthrough()` 只使用 N4 payload 的 `triggered_periods/all_trigger_periods/primary_trigger_period`。
  - 保留 `BUY_HINT/SELL_HINT` 的合法 30m projection passthrough，但不把它伪造成 formal M/W/D。

- [src/ashare_v3/action/dry_run.py](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/action/dry_run.py:461)
  - 新增 `evaluate_n4_formal_trigger_period_proof()`。
  - 普通 formal `TriggerMatched` 若只有 `trigger_period=30m` 且 formal periods 为空，N5 fail-closed 为 `ActionBlocked(n4_formal_trigger_period_missing)`。

- [src/ashare_v3/trigger/rule_v4_matcher.py](/Users/chuanfuchen/Documents/A股监控系统v3/src/ashare_v3/trigger/rule_v4_matcher.py:433)
  - `_evaluate_period()` 读取 `trigger_previous_*` 字段。
  - 缺 `trigger_previous_*` 不 fallback，进入 `TriggerPendingMarketData`。
  - 缺金额单位证明或单位不一致都进入 pending。

## 只读历史审计

只读连接本地 v3 PostgreSQL，未写数据库。

- `20260612/20260615` N4 `TriggerMatched` rows: `82395`
- 普通 formal 条件中 `trigger_period=30m` 且 formal periods 为空的 N4 rows: `71263`
- 这些 rows 全部来自 `20260612`
- 关联到上述 N4 rows 的 N5 rows: `23845`
- N5 已写出 formal M/W/D 的历史污染 rows: `23845`

具体样本 `common_trigger_match.trigger_match_id=253831`：

- N4: `condition_key=BUY:M,W,D`, `trigger_period=30m`, `triggered_periods=[]`, `all_trigger_periods=["30m"]`
- N5 旧事实: `ActionExecuted`, `triggered_periods=["M","W","D"]`
- 结论：这类历史事实必须后续用新 run_id replay/supersede，或走 scoped rollback gate；本轮不静默改写历史事实。

## 验证

- `PYTHONPATH=src:scripts python3 -m unittest tests.test_action_execute tests.test_action_dry_run tests.test_n4_trigger_rule_v4_matcher tests.test_trigger_projection_matcher tests.test_trigger_action_confirmation_metric_matcher`: PASS, `142` tests
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_trigger*.py'`: PASS, `140` tests
- `python3 -m compileall src/ashare_v3/action src/ashare_v3/trigger ...`: PASS
- `PYTHONPATH=src:scripts python3 scripts/check_n4_contract.py`: PASS, `finding_count=0`
- `git diff --check` on scoped touched files: PASS

## Forbidden Scope

- 未执行 N4/N5 runner
- 未写数据库
- 未消费或 update outbox / inbox / checkpoint
- 未启动 scheduler / worker
- 未进入 N6
- 未触碰 voice / mobile / sim / position / order / real trade
- 未读取或修改旧系统

## Next Gate

`N4_N5_TRIGGER_PERIOD_BASELINE_ALIGNMENT_POST_REVIEW_GATE`

后续若要清理用户界面里的旧错消息，应单独进入 scoped rollback / supersession / replay gate，用新 run_id 登记，不得静默改历史 run 证据。
