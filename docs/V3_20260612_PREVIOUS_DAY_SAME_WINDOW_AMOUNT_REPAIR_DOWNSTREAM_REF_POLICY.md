# V3 20260612 Previous Day Same Window Amount Repair Downstream Ref Policy

Result: `POLICY_PASS`

## Decision

Recommended route:

`ROLLBACK_STALE_N5_THEN_REFRESH_N3_REPAIR_SQL_ALLOW_REVIEWED_N4_REFS`

Do not execute the current N3 repair SQL as-is. It is statically safe, but intentionally blocks because N4/N5 refs already exist.

Do not rollback N4 now. N4 did not write final `action_mark`; it only carries `trigger_mark_candidate` and `source_action_confirmation_metric_id`, which are still valid trigger evidence.

Do not create a new projection run now. That would force N4 replay and still leave the stale N5 output to clean up.

## Current Ref Proof

Target projection run:

`action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1`

Refs to target metric run:

| location | refs |
|---|---:|
| common_event_outbox | 4497 |
| common_trigger_match | 4454 |
| common_action_event | 43 |
| user_signal_projection | 0 |

N4 run:

`v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`

- `common_trigger_run=1`
- `common_trigger_match=4454`
- `common_trigger_state=4454`
- `common_trigger_quality_item=10`
- N4 outbox total `4454`
- `TriggerMatched=49`
- `TriggerPendingMarketData=4405`
- outbox pending `4454`
- delivered/delivering `0`
- N4 outbox `action_mark_present=0`
- N5 inbox refs `4454`
- N5 action run refs `1`

N5 stale run:

`v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1`

- `common_action_run=1`
- `common_action_quality_item=4405`
- `common_action_event=43`
- stock/index/board action facts `33/0/10`
- N5 outbox total/pending `43/43`
- delivered/delivering `0`
- downstream inbox refs `0`
- non-scoped consumer inbox refs for N4 source `0`

## Option Review

### Option 1: N5 rollback/supersede, then N3 repair SQL refresh

Decision: `RECOMMENDED`

Reason:

- N5 output is stale under N5-owned final `action_mark`.
- N5 outbox is still pending and has no downstream inbox refs.
- N4 is still useful and does not contain final `action_mark`.
- After stale N5 is removed, N3 can do reviewed additive backfill while preserving N4 trace lineage.

Required controls:

- N5 scoped rollback final gate review before deleting stale N5 rows.
- N3 repair SQL must be refreshed to allow reviewed N4 refs but continue blocking N5/N6 refs.
- N5 replay preflight must be regenerated after N3 post-review.

### Option 2: Rollback N4 and N5, then execute original SQL

Decision: `NOT_RECOMMENDED`

This would work only after N5 rollback, but it unnecessarily deletes 4454 N4 trigger rows/outbox and forces N4 replay. It expands the blast radius without adding semantic safety.

### Option 3: Generate a new projection_run_id

Decision: `NOT_RECOMMENDED`

This avoids modifying already referenced N3 rows, but requires N4 replay and still requires stale N5 cleanup. It creates extra lineage complexity while leaving the main stale-output problem unsolved.

## Recommended Sequence

1. `runtime_control`: read-only stale N5 rollback final gate review.
2. `N5_action`: if user confirms, scoped rollback only stale N5 run/outbox/inbox/checkpoint rows.
3. `N3_market_data`: refresh N3 repair SQL to allow reviewed N4 refs and block N5/N6 refs.
4. `runtime_control`: retry N3 repair execute final gate review.
5. `N5_action`: after N3 repair execute/post-review, regenerate N5 replay dry-run/preflight with N5-owned `action_mark`.

## N3 Repair SQL Policy

Current SQL:

`sql/V3_20260612_realtime_virtual_metric_previous_day_same_window_amount_repair.sql`

Current status:

- static safety: `PASS`
- live status: `BLOCKED`

Required refresh:

- allow reviewed N4 refs
- block N5 refs
- block N6/user refs
- keep default hard-fail before `ALTER/UPDATE`
- keep target `projection_run_id` scope
- keep additive column and scoped backfill only
- forbid `DROP/TRUNCATE/CASCADE`

## Forbidden Scope Proof

This gate did not:

- execute SQL
- write DB
- execute rollback
- consume/update outbox/inbox/checkpoint
- execute N4/N5
- enter N6
- touch voice/mobile/sim/trade
- modify old system

Only artifact inspection and live DB read-only `SELECT` probes were used.

## Next Prompt

```text
layer_role=runtime_control。

进入 V3_20260612_STALE_N5_ACTION_MARK_RUN_ROLLBACK_FINAL_GATE_REVIEW。

目标：只读复核 20260612 stale N5 action_mark run 是否允许进入 N5_action scoped rollback 用户确认点。当前 N5 run v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1 使用旧 trigger_mark_candidate-derived action_mark 口径，N5 outbox total/pending=43/43，delivered/delivering=0/0，N6/user refs=0；N4 run 保留不回滚。不得执行 rollback、不写 DB、不消费/update outbox/inbox/checkpoint、不进入 N4/N5/N6/voice/mobile/sim/trade。请复核 rollback SQL hard-fail guards、scope 仅 stale N5 run + scoped N5 consumer inbox/checkpoint、N4/N3 不变，并输出 PASS/BLOCKED、allowed rollback command draft、forbidden scope proof、rollback 后路线：N3 repair SQL refresh allow reviewed N4 refs。
```
