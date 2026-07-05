# V3 20260612 Realtime Virtual Metric Source Payload Blocked Handoff

Result: `BLOCKED`

The source payload cannot be safely generated from current approved V3 artifacts.

## Why

The writer needs a full 100-row candidate list:

- `B_BUY=76`
- `S_SELL=24`

Current approved V3 artifacts only contain aggregate counts and samples:

- `metric_ready=100`
- `sample_metrics=20`
- `sample_blocked_rows=4`

Generating the payload from samples or random N4 context rows would be inventing input. That would make the next writer execute meaningless.

## What Is Still Ready

- retained 1m source facts: stock/index/board = `705120/90144/56832`
- reviewed N4 context rows: stock/index/board/total = `3982/199/273/4454`
- writer implementation: `POST_REVIEW_PASS`
- scheduler: `not_loaded`
- writer preflight still correctly keeps P1: `source_payload_artifact_required_before_execute_final_gate`

## Needed Authorization

Preferred route:

Allow read-only reference to:

`/Users/chuanfuchen/stock_monitor_isolated/data/monitor.db`

Limited tables:

- `action_fact_cache`
- `minute_kline`

Purpose:

Rebuild the exact 100-row 20260612 B_BUY/S_SELL candidate list for V3 source payload only.

Still forbidden:

- modifying old system DB
- starting old services
- writing V3 DB
- executing writer
- starting scheduler
- entering N4/N5/N6
- consuming/updating outbox/inbox/checkpoint
- voice/mobile/sim/trade

Alternative:

Provide an approved full candidate artifact with 100 rows.

## Next Prompt

```text
layer_role=runtime_control。

进入 V3_20260612_REALTIME_VIRTUAL_METRIC_SOURCE_PAYLOAD_CANDIDATE_SOURCE_AUTHORIZATION_GATE。

目标：确认是否允许只读参考旧系统 /Users/chuanfuchen/stock_monitor_isolated/data/monitor.db 的 action_fact_cache/minute_kline，重建 20260612 B_BUY=76/S_SELL=24 的完整 100 条候选清单，仅用于生成 V3 source_payload artifact。

要求：不修改旧系统，不写 V3 DB，不执行 writer，不启动 scheduler，不进入 N4/N5/N6，不消费/update outbox/inbox/checkpoint，不触碰 voice/mobile/sim/trade。

若确认允许，下一步交给 N3_market_data 生成 payload；若不允许，请提供 approved full candidate artifact。
```
