# N6 Replay Local Canonical Plan

更新日期：2026-06-27
范围：登记 `/n6/replay` local-only replay 已可人工使用/演示；本文档只描述 N6 user 层只读 replay 能力、artifact、安全边界与验收证据，不授权任何 runtime execute、数据库写入、outbox/inbox/checkpoint 消费或 worker。

## 1. 定位

`/n6/replay` 是 N6 user 层的本地 artifact replay 页面，用于：

- 本地重建 N3P/B2 plan-only 输出
- 复用主链路 N4 matcher/lifecycle 与 N5 planner/evaluator 的 dry-run 语义
- 生成 N3/N4/N5 replay messages、timeline、summary 和 Excel 供人工排查

硬边界：

- local replay only
- not production lineage
- not eligible for N6 delivery / voice / mobile / sim / real trade

## 2. 路由与 API

页面路由：

- `GET /n6/replay`

API：

- `GET /api/n6/ui/v1/replay/dates`
- `POST /api/n6/ui/v1/replay/jobs`
- `GET /api/n6/ui/v1/replay/jobs/{job_id}`
- `GET /api/n6/ui/v1/replay/jobs/{job_id}/timeline`
- `GET /api/n6/ui/v1/replay/jobs/{job_id}/n4-messages`
- `GET /api/n6/ui/v1/replay/jobs/{job_id}/n5-messages`
- `GET /api/n6/ui/v1/replay/jobs/{job_id}/export.xlsx`

`POST /api/n6/ui/v1/replay/jobs` 输入约束：

- `mode` 只允许 `local_only`
- `replay_engine_version` 白名单：
  - `fixture_v1`
  - `canonical_plan_v1`
- 默认 engine：
  - `canonical_plan_v1`
- 非白名单 engine fail closed：
  - `BLOCKED_REPLAY_SIDE_EFFECT_RISK`

## 3. Replay Engines

### `fixture_v1`

用途：

- 固定 fixture harness
- 用于基础 UI/API/artifact 冒烟

文案：

- `fixture harness, not canonical planner proof`

限制：

- 不代表 canonical planner proof
- 不得作为生产 lineage 证据

### `canonical_plan_v1`

用途：

- 复用 N3P/B2 plan-only wrapper
- 复用 canonical N4 ordinary/hint matcher + lifecycle
- 复用 canonical N5 ActionEligible + ActionExecuted dry-run evaluator

文案：

- `canonical planner dry-run, not production lineage`

语义：

- `BUY_HINT / SELL_HINT` 可进入 `ActionEligible`
- runtime `signal_type` 仍只收口为 `B_BUY / S_SELL`
- B2/Hint 不得成为 `ActionExecuted` final proof
- `ActionExecuted` final proof 只来自 N3P standard metric
- `TriggerStateChanged / TriggerPendingMarketData` 不得产生 `ActionExecuted`

## 4. Artifact Layout

artifact 路径：

```text
docs/replay/<YYYYMMDD>/<job_id>/
```

`job_id` 约束：

- 必须是 `local_replay_*`
- 不允许 production-like run_id

标准文件：

- `replay_config.json`
- `replay_status.json`
- `replay_timeline.jsonl`
- `n3_messages.jsonl`
- `n4_messages.jsonl`
- `n5_messages.jsonl`
- `replay_summary.json`
- `replay_summary.md`
- `n3_n5_full_day_replay.xlsx`

## 5. 页面与导出

页面能力：

- engine selector，默认 `canonical_plan_v1`
- 顶部固定 disclaimer：
  - `LOCAL REPLAY ONLY / No DB write / No outbox consumption / No checkpoint update`
- Summary 显示：
  - `replay_engine_version`
  - `source_mode=replay`
  - `source_policy`
  - `database_write=false`
  - `consume_outbox=false`
  - `update_checkpoint=false`
- timeline 面板：
  - 展示每分钟 N4/N5 消息数量
  - 点击分钟后过滤 N4/N5 tables

N4 debug columns：

- `original_condition_key`
- `trigger_mark_candidate`
- `source_mode`
- `source_policy`
- `replay_engine_version`
- `trace_summary`
- `lineage_summary`

N5 debug columns：

- `original_condition_key`
- `source_trigger_run_id`
- `source_trigger_event_type`
- `final_proof_source`
- `confirmation_metric_id`
- `action_mark`
- `replay_engine_version`

Excel sheets：

- `summary`
- `minute_timeline`
- `n4_ordinary_messages`
- `n4_hint_messages`
- `n5_action_eligible`
- `n5_action_executed`
- `n5_action_skipped`
- `quality_blockers`
- `lineage_and_safety`

## 6. Safety Flags

标准 safety flags：

```text
replay_mode=local_only
database_write=false
consume_outbox=false
update_checkpoint=false
worker_started=false
production_run_id_used=false
```

plan-only side-effect 约束：

```text
database_written=false
business_rows_written=false
outbox_inbox_checkpoint_consumed_or_updated=false
worker_started=false
launchd_touched=false
runtime_executed=false
```

## 7. 明确禁止事项

- local replay artifact 不得作为 production run_id 或 production lineage
- 不得写 `common_market_data_* / common_trigger_* / common_action_* / common_event_*` 表
- 不得消费生产 `outbox / inbox / checkpoint`
- 不得进入 N6 `delivery / voice / mobile / sim / real trade`
- 不得启动 worker / scheduler / launchd
- 不得把 replay 问题直接修成主链路事实变更；若发现主链路问题，只能另开对应 N3/N4/N5 patch gate

## 8. 验收证据

20260626 canonical local smoke：

- `job_id=local_replay_20260626_154127_3a789ce6`
- verdict：
  - `N6_A_TRACK_REPLAY_20260626_CANONICAL_LOCAL_SMOKE_PASS`

20260627 final acceptance：

- `job_id=local_replay_20260626_155558_035f00b6`
- 页面/API/Excel/artifact 只读验收通过
- 浏览器登录验收：
  - passed

DB no mutation proof 摘要：

- `common_market_data_run` unchanged
- `common_trigger_run / common_trigger_state / common_trigger_match` unchanged
- `common_action_run / common_action_event / stock_action_fact / index_action_fact / board_action_fact` unchanged
- `common_event_outbox / common_event_inbox / common_event_consumer_checkpoint` unchanged

## 9. 当前结论

当前 `/n6/replay` local-only canonical replay 已可人工使用 / 演示，但仅限：

- local artifact inspection
- canonical planner dry-run explanation
- N4/N5 lineage / proof debugging

不等价于：

- production replay execute
- shadow DB execute
- downstream delivery / voice / mobile / sim / trade runtime

## 10. 下一步建议

- 当前状态：
  - ready for manual use / demo
- 若要支持更真实历史全量源：
  - 另开 `N6_REPLAY_HISTORICAL_SOURCE_CONNECTOR_DESIGN_GATE`
- 若要支持 shadow DB：
  - 另开独立隔离设计 gate
  - 不得混入当前 local-only 模式
