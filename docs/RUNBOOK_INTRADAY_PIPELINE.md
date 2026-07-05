# Intraday N3-B1 -> N4 -> N5 Pipeline Runbook

更新日期：2026-06-02

范围：`runtime_control` 只读 runbook / checker，用于盘中 run-once 链路设计和 readiness 检查。本文档不授权 execute、数据库写入、rollback、outbox consumption、worker、N5 delivery、N6 notification、push/voice/mobile/sim/position/real trade。

## 1. Readiness 检查

进入盘中链路前先运行只读 checker：

```bash
PYTHONPATH=src python3 scripts/plan_intraday_pipeline_readiness.py \
  --for-trade-date <FOR_TRADE_DATE> \
  --minute-label <HHMM> \
  --condition-run-id <CONDITION_RUN_ID> \
  --b1-label <B1_LABEL> \
  --json
```

checker 只读：

```text
docs/*.json
sql/*.sql
```

checker 不连接数据库、不执行 N3/N4/N5、不执行 rollback、不消费 outbox、不启动 worker、不触发 delivery/notification/downstream。

readiness 必须确认：

```text
run_id rules = PASS
rollback registry = PASS / WARNING
B1 / C1 / N3 action metric / N4 / N5 status in PASS/WARNING
missing rollback paths = []
P0 = 0
C2/C3 marked as separate gate
worker / consumer process check = manual pre-execute check required
outbox / inbox / checkpoint DB refs = manual pre-execute check required
```

`WARNING` 不是 execute 授权。它表示 checker 已找到可继续人工复核的非阻断项，例如 P1/P2 quality、rollback SQL 非 hard-fail、或需要人工复查 worker/consumer 进程。

## 2. B1 Realtime Snapshot 输入 / 输出

输入：

```text
for_trade_date
market_data_subscription_run_id
common_market_data_subscription where required_data_kind=realtime_daily_snapshot
common_market_data_pull_plan
trade calendar open=true
行情 adapter readiness
```

输出：

```text
common_market_data_run
common_market_data_quality_item
stock/index/board_realtime_daily_snapshot
common_event_outbox:
  MarketSnapshotUpdated
  MarketDataDelayed
  MarketDataMissing
```

边界：

```text
B1 可以写 N3 snapshot facts 和 N3 outbox。
B1 不进入 N4/N5/N6。
B1 不消费 outbox。
B1 不启动 worker。
```

## 3. C1 / C2 / C3 Policy

盘中最小 live 主链路是：

```text
B1 realtime snapshot -> N3 action-confirmation projection -> N4 -> N5
```

C1/C2/C3 归属：

```text
C1 today_minute_bar_1m:
  属于本链路的支撑输入。
  N3 action-confirmation projection facts 需要 C1 今日分钟事实和 A1 前日分钟事实。

C2 closed 30m summary / enrichment:
  不属于最小 live 主链路。
  只作为强确认、回放校验、盘后增强或 replay lane。

C3 MinuteBarClosed:
  不属于最小 live 主链路。
  只作为闭合分钟事件、强确认、replay 或 audit lane。
```

C2/C3 必须另走独立 gate、独立 run_id、独立 rollback，不得顺手塞进 B1 -> N4 -> N5 run-once。

## 4. N3 Action-Confirmation Projection 输入 / 输出

输入：

```text
B1 snapshot_run_id
C1 today_minute_run_id
A1 previous_day_minute_run_id
source_condition_run_id
```

输出：

```text
common_market_data_run
common_market_data_quality_item
stock/index/board_action_confirmation_projection_metric
```

边界：

```text
不写 outbox。
不消费 outbox。
不进入 N4/N5/N6。
不拉行情。
不启动 worker。
```

N3 owns:

```text
current_price
previous 1m/5m/30m/120m body high/low
current_1m_amount / previous_1m_amount
current_5m_virtual_amount / previous_5m_full_amount
first-period boundary fields
source_fact_ids / source_minute_refs / previous_day_minute_refs
metric_ready
```

N4/N5 不得从 raw minute 重算这些指标。

## 5. N4 Trigger 输入 / 输出

输入：

```text
N3 MarketSnapshotUpdated outbox events
N3 stock/index/board_action_confirmation_projection_metric
N4 localized trigger context from source_condition_run_id
```

输出：

```text
common_trigger_run
common_trigger_quality_item
common_trigger_state
common_trigger_match
common_event_outbox:
  TriggerMatched
  TriggerPendingMarketData
  TriggerStateChanged
common_event_inbox / common_event_consumer_checkpoint for consumed N3 events
```

边界：

```text
N4 不拉行情。
N4 不读 raw minute 拼 1m/5m/30m/120m 指标。
N4 不重算 N2 condition。
N4 不决定 final action_mark。
N4 不写 N5/N6。
```

`TriggerMatched` 是 N5 唯一动作确认入口。`TriggerPendingMarketData` 和 `TriggerStateChanged` 只能 no-op / quality / state。

## 6. N5 Action 输入 / 输出

输入：

```text
N4 TriggerMatched only
N3 stock/index/board_action_confirmation_projection_metric
N4 trigger payload trace
```

输出：

```text
common_action_run
common_action_quality_item
stock/index/board_action_fact
common_action_event
common_event_outbox:
  ActionExecuted
  ActionBlocked
  ActionEligible
  ActionSkipped
common_event_inbox / common_event_consumer_checkpoint for consumed N4 events
```

边界：

```text
N5 不消费 TriggerPendingMarketData 创建 action confirmation。
N5 不信任 opaque payload.action_confirmation。
N5 不读 raw minute 拼 1m/5m/30m/120m 指标。
N5 不写 N6 user projection。
N5 不写 sim / position / real trade。
N5 不回写 N4。
```

`ActionExecuted` 只表示 N5 动作确认事实成立，不表示真实下单、sim、通知或交易意图。

## 7. Run ID 规则

```text
N3 subscription:
market_data_subscription_<FOR_TRADE_DATE>_<CONDITION_RUN_ID>

B1 snapshot:
realtime_snapshot_<FOR_TRADE_DATE>_<B1_LABEL>_<SUBSCRIPTION_RUN_ID>

C1 today minute:
today_minute_bar_1m_<FOR_TRADE_DATE>_until_<HHMM>__<SUBSCRIPTION_RUN_ID>

N3 action-confirmation projection:
action_confirmation_projection_metric_<FOR_TRADE_DATE>_<HHMM>__<B1_SNAPSHOT_RUN_ID>

N4 trigger execute:
trigger_action_confirmation_metric_execute_<FOR_TRADE_DATE>_<HHMM>__<CONDITION_RUN_ID>

N5 action execute:
action_consumer_action_confirmation_metric_execute_<FOR_TRADE_DATE>_<HHMM>__<N4_EXECUTE_RUN_ID>
```

同一 run_id 不得覆盖重跑。需要重跑时必须另走 rebuild / retry gate，并追加：

```text
_rebuild_<YYYYMMDD>_vN
_retry<N>
_live<N>
```

## 8. Rollback 规则

rollback registry 至少包含：

```text
sql/N3_B1_realtime_snapshot_<FOR_TRADE_DATE>_<B1_LABEL>_rollback.sql
sql/N3_C1_today_minute_bar_1m_<FOR_TRADE_DATE>_until_<HHMM>_rollback.sql
sql/N3_action_confirmation_projection_metric_business_rollback.sql
sql/N4_action_confirmation_metric_business_execute_rollback.sql
sql/N5_<FOR_TRADE_DATE>_action_confirmation_metric_execute_rollback.sql
```

rollback scope：

```text
B1: snapshot_run_id
C1: today_minute_run_id
N3 action metric: projection_run_id
N4: execute_run_id
N5: action_run_id + source_trigger_run_id + consumer_name
```

rollback 执行必须另走对应 layer gate。runtime_control 只登记和检查路径，不执行 SQL。

DELETE 前建议 hard-fail guard：

```text
delivered / delivering outbox refs
downstream inbox refs
consumer checkpoint refs
N4/N5/N6/user downstream refs
voice/mobile/sim/position/real trade refs
```

## 9. Worker / Replay / Idempotency

worker 不属于本 runbook 的必要条件。

推进顺序：

```text
run-once dry-run/preflight
-> run-once execute
-> post-review
-> bounded worker smoke
-> long-running worker
```

idempotency 必须满足：

```text
event_id stable
dedup_key stable
consumer_name stable
source_run_id scoped
inbox idempotent
checkpoint monotonic
same event re-consume no duplicate facts
same run_id re-execute BLOCKED unless rollback/rebuild gate
```

Replay 分两类：

```text
live replay:
  复放 N3/N4 outbox pending events，要求不重复写 facts/outbox。

closed-minute replay:
  基于 C2/C3 / MinuteBarClosed / closed summary 做 audit 或强确认。
  不覆盖 live run，必须独立 replay_run_id。
```

## 10. Fail-Fast 条件

立即 BLOCKED：

```text
missing artifact
missing rollback SQL path
run_id rule mismatch
P0 > 0
worker / consumer risk 无法解释
delivered / delivering outbox refs
downstream inbox / checkpoint refs
N4/N5/N6 forbidden refs
N4 读取 raw minute 或自行拼 action-confirmation metric
N5 消费 TriggerPendingMarketData 创建 action confirmation
N5 信任 opaque action_confirmation 作为最终确认
任何 push / voice / mobile / sim / position / real trade
```

## 11. 一页 Runbook

```text
1. runtime_control:
   run read-only intraday checker.

2. N3_market_data:
   B1 dry-run/preflight.
   Execute B1 only after explicit user confirmation.
   Return to runtime_control registration.

3. N3_market_data:
   Ensure C1 today minute and A1 previous-day minute are ready.
   Execute N3 action-confirmation projection only after explicit user confirmation.
   Return to runtime_control registration.

4. N4_trigger:
   Dry-run/final gate.
   Execute N4 only after explicit user confirmation.
   Return to runtime_control registration.

5. N5_action:
   Dry-run/final gate.
   Execute N5 only after explicit user confirmation.
   Return to runtime_control registration.

6. Stop.
   Do not deliver N5 outbox.
   Do not enter N6.
   Do not start worker.
   Do not push/voice/mobile/sim/position/real trade.
```
