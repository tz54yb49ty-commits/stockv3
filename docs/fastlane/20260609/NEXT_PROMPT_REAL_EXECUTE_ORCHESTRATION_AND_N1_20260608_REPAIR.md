# Next Prompt: Real Execute Orchestration And N1 20260608 Repair

Use this prompt after the 20260609 Fast Lane pilot BLOCKED handoff.

```text
layer_role=runtime_control。

进入 RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_REAL_EXECUTE_ORCHESTRATION_ALIGNMENT_GATE。

目标：解决 20260609 Fast Lane pilot 的两个 P0 阻断，并决定后续 gate 顺序：
1. Fast Lane wrapper 当前只支持 child-step-json validation/report assembly，不能真实编排同层 guarded runner。
2. 20260609 的 source_trade_date=20260608，但 20260608 N1 official daily / daily_basic / financial / condition-source facts 当前为 0，且没有 dedicated 20260608 guarded N1 runner。

依据：
- docs/fastlane/20260609/01_runtime_readiness.md/json
- docs/fastlane/20260609/BLOCKED_runner_capability_handoff.md/json
- docs/fastlane/20260609/BLOCKED_n1_source_fact_and_runner_handoff.md/json
- docs/fastlane/20260609/NEXT_PROMPT_REAL_EXECUTE_ORCHESTRATION_AND_N1_20260608_REPAIR.md/json
- src/ashare_v3/runtime/fastlane_contract.py
- src/ashare_v3/runtime/fastlane_validation.py
- scripts/run_n1_fastlane_bundle_once.py
- scripts/run_n2_fastlane_bundle_once.py
- scripts/run_n3_a1_fastlane_bundle_once.py
- scripts/run_official_daily_ingestion_20260605_once.py
- scripts/run_condition_source_activation_20260605_once.py
- scripts/run_real_daily_incremental.py

要求：
- 只读 alignment review / contract decision
- 不改代码
- 不写数据库
- 不 execute N1/N2/N3
- 不执行 rollback SQL
- 不消费/update outbox/inbox/checkpoint
- 不启动 worker
- 不进入 N3-B/C/N4/N5/N6
- 不拉实时行情
- 不 proposal/order/trade/sim/position/PnL/real trade
- 不触碰旧系统

请复核：
1. Calendar proof 是否已 PASS：20260609 open，prev_trade_date=20260608。
2. 20260608 N1 source facts 是否仍缺失。
3. 当前 Fast Lane wrappers 是否仍为 validation/report-only。
4. 当前 date-fixed N1 runners 是否只能跑 20260605。
5. generic run_real_daily_incremental.py 是否不满足 Fast Lane guarded execute contract。
6. 是否必须先做 N1_20260608_SOURCE_FACTS_GUARDED_RUNNER_CONTRACT_GATE。
7. 是否必须再做 Fast Lane real same-layer orchestration implementation gate，或决定 first pilot 降级为 dry-run-only。
8. 后续真实 execute 必须保留：--execute --user-confirmed；N1 需要 --postgres-commit-enabled 时必须包含；P0=0；rollback static safe；expected/actual row match；scoped outbox/inbox/checkpoint refs zero；downstream refs zero。

请生成：
- docs/RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_REAL_EXECUTE_ORCHESTRATION_ALIGNMENT.md
- docs/RUNTIME_CONTROL_N1_TO_N3_A1_FAST_LANE_REAL_EXECUTE_ORCHESTRATION_ALIGNMENT.json

输出：
- ALIGNMENT_PASS / BLOCKED
- current blocker proof
- recommended decision:
  - IMPLEMENT_REAL_SAME_LAYER_ORCHESTRATION
  - FIRST_BUILD_N1_20260608_GUARDED_RUNNER
  - DOWNSCOPE_FIRST_PILOT_TO_DRY_RUN_ONLY
  - BLOCKED_NEED_USER_POLICY
- required implementation scope
- required tests
- forbidden scope proof
- next recommended gate
```
