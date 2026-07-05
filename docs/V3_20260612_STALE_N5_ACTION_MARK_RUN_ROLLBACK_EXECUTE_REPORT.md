# V3 20260612 Stale N5 Action Mark Run Rollback Execute Report

Result: `ROLLBACK_BLOCKED_PARTIAL`

Generated at: `2026-06-13 10:02:00 +0800`

This gate executed the scoped rollback SQL once, then performed read-only post-review. A second attempt of the same rollback SQL was blocked by its hard-fail guard before any destructive statement. No N4 rollback was executed, no N3 projection rows were modified, no N5 outbox was consumed, and N6/voice/mobile/sim/position/trade were not entered.

## Scope

- Target action run: `v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1`
- Source N4 trigger run: `v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`
- Scoped consumer: `n5_action_consumer_v1`
- SQL executed: `sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql`
- DB target: `ashare_v3` on `127.0.0.1:5432` as `ashare_v3_user`

## Execution Summary

The first rollback SQL execution committed and reported these deletes:

- `common_event_delivery_attempt=0`
- `common_event_consumer_checkpoint=2082`
- `common_event_inbox=4454`
- `common_event_outbox=43`
- `common_event_ledger=0`
- `common_action_event=43`
- `board_action_fact=10`
- `index_action_fact=0`
- `stock_action_fact=33`
- `common_action_quality_item=4405`
- `common_action_run=1`

However, post-review found the action run / facts / events / outbox still present with timestamps around the rollback execution window. The scoped `n5_action_consumer_v1` inbox/checkpoint rows and quality rows remained cleaned.

A second execution attempt was made using the same SQL to complete the same scoped rollback. It did not delete anything: the hard-fail guard blocked before the first `DELETE`:

```text
N5 rollback blocked: non-scoped consumer inbox refs exist for source_trigger_run_id (49)
```

Read-only proof shows those 49 inbox refs belong to:

```text
consumer_name=v3_realtime_engine_n5_consumer_20260612
received_at=2026-06-13 09:59:11.293845+08
```

Because that consumer is non-scoped for this rollback route, the guard correctly blocked the second attempt.

## Current Post-Check

Remaining target N5 rows:

- `common_action_run=1`
- `common_action_quality_item=0`
- `stock_action_fact=33`
- `index_action_fact=0`
- `board_action_fact=10`
- `common_action_event=43`
- `N5 common_event_outbox=43`
- `N5 common_event_ledger=0`
- `N5 outbox pending=43`
- `N5 outbox delivered/delivering=0`

Scoped consumer cleanup:

- `n5_action_consumer_v1` inbox for scoped N4 source: `0`
- `n5_action_consumer_v1` checkpoint on scoped N4 partitions: `0`

Non-scoped refs now present/preserved:

- non-scoped inbox refs for scoped N4 source: `49`
- non-scoped checkpoint refs on scoped N4 partitions: `6322`

N4 preservation proof:

- `common_trigger_run=1`
- `common_trigger_match=4454`
- `common_trigger_state=4454`
- `N4 common_event_outbox=4454`
- `N4 outbox delivered/delivering=0`

Downstream proof:

- `common_position_state refs=0`
- `common_position_event refs=0`
- N5 outbox delivered/delivering remains `0`

## Interpretation

The rollback is not complete and must not be registered as passed.

The most likely cause is a concurrent short-lived N5 path writing the same stale action run during the rollback window. Process inspection after the event did not find a live v3 N5 worker, but database evidence shows a non-scoped consumer named `v3_realtime_engine_n5_consumer_20260612` wrote 49 inbox refs at the same timestamp as the residual action run rows.

## Boundary Proof

- N4 trigger facts/outbox status were preserved.
- N3 projection / metric facts were not modified by this gate.
- N5 outbox was not consumed or updated to delivered/delivering.
- N6/user/voice/mobile/sim/position/trade were not entered.
- Old system was not modified by this gate.

Note: process inspection showed an unrelated old-system process under `/Users/chuanfuchen/stock_monitor_isolated`, but this gate did not touch or control it.

## Required Next Gate

Return to runtime_control for a rollback failure / supersession review. Recommended next decision:

1. Identify and stop or isolate `v3_realtime_engine_n5_consumer_20260612` / any source capable of writing the stale N5 action run.
2. Decide whether the non-scoped `v3_realtime_engine_n5_consumer_20260612` rows are part of the stale lineage and should be included in a new explicitly scoped rollback.
3. Generate a new rollback final gate if cleanup is still desired.

Do not enter N6 and do not consume the remaining N5 outbox until this is resolved.
