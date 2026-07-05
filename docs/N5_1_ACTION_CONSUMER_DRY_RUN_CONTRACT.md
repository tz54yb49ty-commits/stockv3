# N5-1 Action Consumer Dry-Run Contract

## Scope

N5-1 只设计并验证 N5 如何消费 N4 标准事件。

本阶段不执行真实消费，不写 `action_decision / action_event`，不写 N5 outbox，不更新 `common_event_inbox / common_event_consumer_checkpoint`，不启动 worker，不进入 N6。

## Consumer Identity

默认 consumer：

```text
consumer_name = n5_action_consumer_v1
source_layer = N4_trigger
```

只接受：

```text
TriggerMatched
TriggerCleared
TriggerPendingMarketData
```

## Ordering

N5-1 dry-run 按以下顺序构造消费计划：

```text
partition_key
event_time
outbox_id
event_id
```

`partition_key` 必须来自 N4 event envelope，当前等价于 `identity_key`，用于同一对象的顺序约束。

## Dedup

N5 consumer 未来必须按两类键幂等：

```text
consumer_name + event_id
consumer_name + source_layer + event_type + source_run_id + dedup_key + event_schema_version
```

N5-1 dry-run 对重复事件只生成 `skipped` 计划，不生成重复 action candidate。

## Inbox / Checkpoint Plan

N5-1 只输出写入计划，不执行写入：

```text
would_insert_common_event_inbox = true/false
would_update_consumer_checkpoint = true/false
executed = false
```

checkpoint 计划键：

```text
consumer_name + partition_key + source_layer
```

checkpoint 计划字段：

```text
last_event_id
last_event_time
last_outbox_id
checkpoint_payload
```

## Action Candidate Mapping

N5-1 复用 N5-0 action candidate dry-run：

```text
TriggerMatched -> action_candidate
TriggerCleared -> clear_candidate
TriggerPendingMarketData -> quality_plan / pending_market_data
```

`TriggerPendingMarketData` 不得生成实际 `ActionEvent` 候选。

`BUY_HINT / SELL_HINT` 必须保留为标准买卖动作候选，不得在 consumer 阶段丢弃。

## Commands

```bash
PYTHONPATH=src python3 scripts/plan_action_consumer_dry_run.py \
  --trigger-run-id trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute
```

输出：

```text
docs/N5_1_action_consumer_dry_run_report.json
docs/N5_1_ACTION_CONSUMER_DRY_RUN_REPORT.md
```

## Boundary

N5-1 禁止：

```text
写 action fact
写 N5 common_event_outbox
更新 common_event_inbox
更新 common_event_consumer_checkpoint
更新 N4 outbox status
拉行情
启动 worker
写 N6 user projection
写 voice / sim / real trade
```
