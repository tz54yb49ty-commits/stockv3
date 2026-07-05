# V3 20260612 N4/N5 Runtime Replay Readiness After N5 Action Mark Alignment

Result: `BLOCKED`

## Decision

不允许直接进入 N4/N5 replay contract/preflight。

结论分层如下：

- N4 不需要重跑：N4 当前 payload 只写 `trigger_mark_candidate` 与 `source_action_confirmation_metric_id`，没有写 final `action_mark`。
- N5 需要重放：当前 N5 action fact/outbox 是旧口径，`action_mark` 仍等同于 `trigger_mark_candidate`，trace 缺少 `n4_trigger_mark_candidate / action_mark_source / action_mark_basis / action_mark_reason`。
- N5 重放前必须先回 N3 修复：当前 20260612 N3 action-confirmation metric live schema/rows 还不具备 `previous_day_same_window_amount`，无法支撑 N5-owned final `action_mark` 的生产口径。

Recommended route:

`REPAIR_N3_PREVIOUS_DAY_SAME_WINDOW_AMOUNT_THEN_N5_SCOPED_REPLAY`

## N5 Action Mark Alignment Proof

Source artifact:

- `docs/N5_ACTION_MARK_N5_OWNED_DERIVATION_POST_REVIEW.json`

Post-review result: `POST_REVIEW_PASS`

Registered rules:

- final `action_mark` is owned by N5.
- N4 `trigger_mark_candidate` is trace-only.
- `previous_day_same_window_amount` means previous trading day same 30m time-window amount.
- Missing `previous_day_same_window_amount` does not block `ActionExecuted`; it downgrades `action_mark=normal` and writes trace reason `previous_day_same_window_amount_missing`.

Validation registered there:

- targeted N5/N3 tests: `137 OK`
- `test_n5*.py`: `5 OK`
- JSON parse: `PASS`
- compileall: `PASS`
- `scripts/check_n4_contract.py`: `PASS`
- `git diff --check`: `PASS`

## Current Artifact Proof

### N4

N4 current artifacts are not stale for this specific alignment:

- contract: `docs/V3_20260612_N4_ACTION_CONFIRMATION_METRIC_BUSINESS_EXECUTE_CONTRACT_AFTER_N3_WRITER.json`
- dry-run: `docs/V3_20260612_N4_ACTION_CONFIRMATION_METRIC_DRY_RUN_AFTER_N3_WRITER.json`
- dry-run result: `DRY_RUN_PASS`
- candidates: `4454`
- `TriggerMatched`: `49`
- `TriggerPendingMarketData`: `4405`
- contract `final_action_mark_written_by_n4=false`
- live N4 outbox has `action_mark_present=0`
- live N4 outbox has `trigger_mark_candidate_present=4454`
- live N4 outbox has `source_action_confirmation_metric_id_present=4454`

Decision: `N4_REPLAY_NOT_REQUIRED`.

### N5

N5 current artifacts and live rows are stale under the new action_mark ownership:

- dry-run: `docs/V3_20260612_N5_ACTION_CONSUMER_DRY_RUN_AFTER_N4_ACTION_CONFIRMATION_METRIC.json`
- execute report: `docs/V3_20260612_N5_ACTION_CONSUMER_EXECUTE_REPORT_AFTER_N4_ACTION_CONFIRMATION_METRIC.json`
- post-review: `docs/V3_20260612_N5_ACTION_CONSUMER_EXECUTE_POST_REVIEW_AFTER_N4_ACTION_CONFIRMATION_METRIC.json`

Live stale run:

`v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1`

Rows:

- `common_action_run=1`
- `common_action_quality_item=4405`
- `stock_action_fact=33`
- `index_action_fact=0`
- `board_action_fact=10`
- `common_action_event=43`
- N5 outbox `total/pending=43/43`
- delivered/delivering `0/0`
- N6 `user_signal_projection` refs `0`

Sample trace shows old shape:

- `action_mark=30m_volume` or `30m_shrink`
- `trigger_mark_candidate` present
- `n4_trigger_mark_candidate=null`
- `action_mark_source=null`
- `action_mark_basis=null`
- `action_mark_reason=null`
- `current_30m_virtual_amount=null`
- `previous_day_same_window_amount=null`

Decision: `N5_REPLAY_REQUIRED_AFTER_N3_METRIC_REPAIR`.

## N3 Metric Input Proof

Projection run:

`action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1`

Live DB: `ashare_v3 / ashare_v3_user / 127.0.0.1:5432`

Current rows:

| asset | rows | current_30m_virtual_amount | previous_30m_full_amount | previous_day_same_window_amount |
|---|---:|---:|---:|---:|
| stock | 62 | 62 | 62 | missing live column |
| index | 0 | 0 | 0 | missing live column |
| board | 38 | 38 | 38 | missing live column |
| total | 100 | 100 | 100 | missing live column |

This blocks canonical N5 replay. The N5 code/schema draft supports the concept, but the live 20260612 N3 metric tables/current run do not yet provide the field.

## Replay Scope Recommendation

1. Do not rerun N4.
2. First enter an N3 repair gate to add/backfill `previous_day_same_window_amount` for the 20260612 realtime/action-confirmation metric run.
3. Then return to runtime_control for N5 scoped replay readiness.
4. Before authoritative N5 replay, handle the stale N5 run/outbox via scoped rollback final gate or an explicit reviewed superseding replay scope.

## Residual Caveat

The existing `source_trigger_state_id` schema migration review assertion remains a non-blocker for this gate. It is registered as unrelated to N5-owned `action_mark` derivation.

## Forbidden Scope Proof

This gate did not:

- execute N4/N5 runner
- write database rows
- execute rollback
- consume/update outbox/inbox/checkpoint
- start worker
- enter N6
- touch voice/mobile/sim/position/order/trade
- modify old system

Only read-only artifact inspection and live DB `SELECT` probes were used.

## Next Prompt

```text
layer_role=N3_market_data。

进入 V3_20260612_REALTIME_VIRTUAL_METRIC_PREVIOUS_DAY_SAME_WINDOW_AMOUNT_REPAIR_GATE。

目标：修复 20260612 N3 realtime/action-confirmation metric 对 previous_day_same_window_amount 的 schema 与数据覆盖，使当前 projection_run_id 的 stock/board 100 条 metric rows 能提供上一交易日同 30m 时间窗口金额，供 N5-owned final action_mark 派生使用。不得执行 N4/N5，不消费/update outbox/inbox/checkpoint，不进入 N6/voice/mobile/sim/position/order/trade。完成后回 runtime_control 做 N5 scoped replay/rollback readiness refresh。
```
