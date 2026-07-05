# N4 Worker Bounded Polling Scheduler Contract

Result: `CONTRACT_PASS`

Layer role: `runtime_control`

Generated at: `2026-06-11T17:11:37+08:00`

This gate only defines the N4 bounded polling scheduler contract. It did not install or enable `launchd`, did not execute N4, did not start a long-running worker, did not write the database, did not execute rollback SQL, and did not enter N5/N6.

## Prerequisites

- N4 bounded smoke closeout: `CLOSEOUT_PASS`
- N4 bounded smoke execute report metadata alignment: `POST_REVIEW_PASS`
- N4 trigger semantic smoke: `POST_REVIEW_PASS`
- N4 worker state transition contract: `CONTRACT_PASS`
- N4 bounded smoke runner implementation: `POST_REVIEW_PASS`

The semantic smoke is valid readiness evidence, but it remains `fixture_only=true` and `not_new_market_decision=true`. Production bounded polling still needs an explicit wrapper/policy review before scheduler activation.

## Scheduler Model

Recommended model: macOS user `launchd` bounded polling.

- Label: `com.ashare-v3.n4.bounded-polling`
- `StartInterval=60`
- `KeepAlive=false`
- `RunAtLoad=false`
- One invocation runs one bounded pass and exits.
- This is not a long-running worker.
- `cron` fallback remains blocked until a wrapper lockfile or external lock guard is implemented and reviewed.

## Wrapper Requirement

Directly scheduling `scripts/run_n4_worker_bounded_smoke_once.py` with a fixed `smoke_run_id` is not safe for repeated polling. Every scheduled pass needs a dynamic run id, report path, status path, and rollback SQL path.

Required wrapper:

`scripts/run_n4_worker_bounded_poll_once.py`

Wrapper rules:

- Default mode is `PLAN_ONLY`.
- Execute mode requires both `--execute` and `--user-confirmed`.
- Each pass derives a unique `smoke_run_id`.
- Each pass derives scoped status, JSON report, Markdown report, and rollback SQL paths.
- Child runner command must be an argv list, not a shell string.
- Child runner must still include `--execute --user-confirmed`.
- The wrapper exits after one bounded pass.

Dynamic id policy:

- `smoke_run_id=n4_worker_bounded_poll_20260611_<YYYYMMDDTHHMMSS+0800>`
- `status_json=docs/N4_WORKER_BOUNDED_POLLING_20260611_<HHMMSS>_STATUS.json`
- `json_report=docs/N4_WORKER_BOUNDED_POLLING_20260611_<HHMMSS>_EXECUTE_REPORT.json`
- `markdown_report=docs/N4_WORKER_BOUNDED_POLLING_20260611_<HHMMSS>_EXECUTE_REPORT.md`
- `rollback_sql=sql/N4_worker_bounded_polling_20260611_<HHMMSS>_rollback.sql`

## Activation Command Draft

Draft only. This command is not approved for execution until wrapper implementation, post-review, preflight refresh, final gate, and user confirmation.

```bash
PYTHONPATH=src:scripts python3 scripts/run_n4_worker_bounded_poll_once.py \
  --for-trade-date 20260611 \
  --source-run-id realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1 \
  --source-event-type MarketSnapshotUpdated \
  --source-trade-date 20260611 \
  --consumer-name n4_trigger_worker_v1_bounded_polling_20260611 \
  --max-events 50 \
  --max-runtime-seconds 120 \
  --heartbeat-interval-seconds 10 \
  --docs-root docs \
  --sql-root sql \
  --tmp-root tmp \
  --execute \
  --user-confirmed
```

## Consumer Naming

Scheduler consumer:

`n4_trigger_worker_v1_bounded_polling_20260611`

This must remain distinct from the prior smoke consumers:

- `n4_trigger_worker_v1_bounded_smoke_20260611_day_scope_probe`
- `n4_trigger_worker_v1_bounded_smoke_20260611_trigger_semantic_probe`

N4 must not update N3 `common_event_outbox` status. N4 acknowledgment remains scoped to its own `common_event_inbox` and `common_event_consumer_checkpoint`.

## No-Overlap Policy

No-overlap v1 uses a single launchd Label:

- Label: `com.ashare-v3.n4.bounded-polling`
- `StartInterval=60`
- `KeepAlive=false`
- `RunAtLoad=false`
- `ProgramArguments` must be an argv list.
- Shell strings are not allowed.

If the same Label is still running when the next interval fires, launchd is expected to miss that interval rather than start a second concurrent job. No lockfile is required for launchd v1. Cron fallback remains blocked until a lock guard is reviewed.

## Stop Policy

Stop is a separate future runtime_control gate. It must unload or disable the launchd Label and verify no scoped process remains.

Draft stop command, not executed:

```bash
launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n4.bounded-polling.plist
```

Stop does not execute rollback SQL and does not modify database rows. If a scheduled pass reports `BLOCKED`, the stop gate should preserve the latest report and produce a handoff.

## Rollback Requirements

Each bounded pass must have a scoped rollback SQL path and the SQL must hard-fail by default before the first row removal.

Rollback scope:

- `common_event_inbox` for the target consumer and target `smoke_run_id`
- `common_event_consumer_checkpoint` for the target consumer and target `smoke_run_id`
- N4 `common_event_outbox` where `source_run_id` is the target `smoke_run_id`
- `common_trigger_match` for the target `smoke_run_id`
- `common_trigger_state` for the target `smoke_run_id`
- `common_trigger_quality_item` for the target `smoke_run_id`
- `common_trigger_run` for the target `smoke_run_id`

Rollback must preserve N3 source facts, N3 outbox status, N5/N6/user/sim/order/trade/position facts, and historical smoke evidence.

Required guards:

- N4 outbox delivered/delivering must be zero.
- N5 refs must be zero.
- N6/user refs must be zero.
- sim/order/trade/position refs must be zero.
- Scoped worker process must not be running.
- No downstream checkpoint refs to target N4 outbox.
- No `DROP`, `TRUNCATE`, or `CASCADE`.

## Decision

Contract status: `CONTRACT_PASS`

Scheduler activation now: `false`

Install/enable scheduler now: `false`

Long-running worker allowed: `false`

Next recommended gate:

`N4_WORKER_BOUNDED_POLLING_RUN_ONCE_WRAPPER_IMPLEMENTATION_GATE`

## Forbidden Scope Proof

- scheduler installed/enabled: `false`
- launchd modified: `false`
- cron modified: `false`
- N4 executed by this gate: `false`
- worker started: `false`
- long-running worker started: `false`
- database written by this gate: `false`
- rollback SQL executed: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- N3 outbox status updated: `false`
- N5 entered: `false`
- N6 entered: `false`
- delivery/push/voice/mobile: `false`
- proposal/order/trade: `false`
- sim/position/PnL/real trade: `false`
- old system touched: `false`

## Next Prompt

```text
layer_role=N4_trigger。

进入 N4_WORKER_BOUNDED_POLLING_RUN_ONCE_WRAPPER_IMPLEMENTATION_GATE。

目标：实现 N4 bounded polling run-once wrapper scripts/run_n4_worker_bounded_poll_once.py。wrapper 默认 plan-only；execute 必须同时具备 --execute --user-confirmed；每轮动态生成 smoke_run_id、status/report/rollback 路径，并以 argv list 调用 scripts/run_n4_worker_bounded_smoke_once.py 的 bounded pass。不得安装/启用 scheduler，不得启动长期 worker，不得进入 N5/N6。
```
