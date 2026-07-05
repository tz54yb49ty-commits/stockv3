# V3 Realtime Engine Production Scheduler Contract

- stage: `V3_REALTIME_ENGINE_PRODUCTION_SCHEDULER_CONTRACT`
- result: `CONTRACT_PASS`
- generated_at: `2026-06-13T07:38:06.895137+08:00`
- scheduler label: `com.ashare-v3.v3-realtime-engine`
- start interval: `3 seconds`
- model: `launchd bounded run-once, no long-running worker`
- activation authorized by this gate: `false`

## Authority Proof

- executable_plan: `PLAN_PASS` expected `PLAN_PASS` passed `True`
- new_plan_runtime_closeout: `CLOSEOUT_PASS` expected `CLOSEOUT_PASS` passed `True`
- n3_writer_post_review: `POST_REVIEW_PASS` expected `POST_REVIEW_PASS` passed `True`
- n4_post_review: `POST_REVIEW_PASS` expected `POST_REVIEW_PASS` passed `True`
- n5_post_review: `POST_REVIEW_PASS` expected `POST_REVIEW_PASS` passed `True`


## Scheduler Model

- wrapper target: `scripts/run_v3_realtime_engine_once.py`
- wrapper exists now: `False`
- no-overlap lock: `tmp/v3_realtime_engine.lock`
- default mode: `PLAN_ONLY`
- execute gate: `--execute --user-confirmed`
- child command policy: `argv list only; no shell string`
- launchd draft: `docs/V3_REALTIME_ENGINE_PRODUCTION_SCHEDULER_LAUNCHD_DRAFT.plist`
- install target: `/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.v3-realtime-engine.plist`

## N3 Contract

N3 owns realtime 1m K / quote / snapshot ingestion and N3-standard realtime virtual metrics. The first production wrapper must preserve the 09:20-09:30 auction virtual 1m policy and the midday bridge policy: do not fabricate 11:30; 13:00 bridges the missing 11:30 and 13:01 compares to 13:00.

## N4 Contract

N4 consumes only N3 standard realtime virtual metric facts/events and emits `TriggerMatched`, `TriggerPendingMarketData`, or `TriggerStateChanged`. N4 must not directly read raw minute rows or call market adapters.

## N5 Contract

N5 consumes only `TriggerMatched` as action-confirmation entry and emits `ActionEligible`, `ActionBlocked`, `ActionExecuted`, or `ActionSkipped`. `ActionExecuted` is only an action-confirmation fact, not order/sim/N6/voice/mobile/real-trade intent.

## Rollback / Stop Registry

- N3 rollback: `sql/V3_20260612_realtime_virtual_metric_writer_runner_rollback.sql`
- N4 rollback: `sql/V3_20260612_n4_action_confirmation_metric_business_execute_after_n3_writer_rollback.sql`
- N5 rollback: `sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql`
- stop command: `launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.v3-realtime-engine.plist`

## Forbidden Scope

This contract gate did not install or enable scheduler, execute wrapper/children, write DB, execute rollback, mutate outbox/inbox/checkpoint, enter N6, or touch voice/mobile/sim/trade/old system.

## Next

`V3_REALTIME_ENGINE_PRODUCTION_RUN_ONCE_WRAPPER_IMPLEMENTATION_GATE`
