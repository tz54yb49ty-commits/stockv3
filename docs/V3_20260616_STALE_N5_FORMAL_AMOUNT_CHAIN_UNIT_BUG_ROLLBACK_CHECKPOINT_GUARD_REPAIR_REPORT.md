# V3 20260616 Stale N5 Formal Amount Chain Unit Bug Rollback Checkpoint Guard Repair Report

Result: `REPAIR_PASS`

Generated at: `2026-06-17 01:38:09 +0800`

This gate did not execute rollback, did not write database rows, did not consume or update outbox/inbox/checkpoint, did not enter N6, did not start worker/scheduler, and did not touch voice/mobile/sim/position/order/real trade.

## Scope

- Layer role: `N5_action`
- Stale N5 action run: `v3_n5_action_replay_20260616_after_n4_trigger_price_repair_v1`
- Source N4 trigger run: `v3_n4_trigger_replay_20260616_until_1401_v1`
- Scoped N5 consumer: `n5_action_consumer_v1_20260616_trigger_price_repair_replay`
- Rollback SQL: `sql/V3_20260616_n5_action_after_n4_trigger_price_repair_rollback.sql`

## Root Cause

The rollback SQL hard-failed when non-scoped consumer checkpoint rows existed on the preserved N4 source partitions.

Live read-only proof:

- scoped N5 outbox total: `540`
- scoped N5 outbox delivered/delivering: `0`
- downstream inbox refs to scoped N5 outbox: `0`
- scoped dedicated consumer N4 inbox rows: `540`
- scoped dedicated consumer N4 checkpoint rows: `452`
- non-scoped N4 checkpoint rows on the same partitions: `3431`
- non-scoped N4 inbox rows on the same source run: `0`

Because this rollback preserves the N4 run and deletes only the scoped N5 run plus this dedicated consumer's N4 inbox/checkpoint rows, those non-scoped N4 checkpoint rows are not downstream refs to the stale N5 action run. They must remain untouched, and they must not block scoped N5 rollback.

## SQL Repair

Changed file:

- `sql/V3_20260616_n5_action_after_n4_trigger_price_repair_rollback.sql`

The repair removed the hard-fail guard that counted:

```sql
common_event_consumer_checkpoint
WHERE source_layer = 'N4_trigger'
  AND consumer_name <> v_consumer_name
  AND partition_key IN (...)
```

The SQL now documents that non-scoped consumer checkpoints on preserved N4 source partitions remain untouched and are not rollback blockers.

## Preserved Guards

The rollback SQL still hard-fails before the first destructive statement when any of the following are present:

- scoped N5 outbox rows with `status IN ('delivering', 'delivered')`
- downstream inbox refs to the scoped N5 outbox/run
- downstream checkpoint refs to the scoped N5 outbox/run
- downstream user / voice / mobile / sim / position refs containing the action run or source trigger run

## Delete Scope

The delete scope remains scoped to:

- stale N5 action rows for `run_id = v3_n5_action_replay_20260616_after_n4_trigger_price_repair_v1`
- N5 outbox / ledger rows for `source_layer='N5_action'` and the stale action run
- `n5_action_consumer_v1_20260616_trigger_price_repair_replay` inbox rows for the scoped N4 source run
- `n5_action_consumer_v1_20260616_trigger_price_repair_replay` checkpoint rows only for partitions derived from those scoped inbox rows

The rollback SQL still does not delete:

- N4 trigger facts
- N4 outbox rows or status
- N3 metric / market-data facts
- N2/N1 facts
- N6/user/voice/mobile/sim/position/order/real-trade facts
- non-scoped consumer checkpoint rows for the preserved N4 source

## Tests

Added:

- `tests/test_v3_20260616_stale_n5_formal_amount_chain_rollback_guard.py`

The test covers:

- reviewed 20260616 scope constants
- hard-fail guard exists before the first destructive statement
- preserved N4 non-scoped checkpoint refs do not block rollback
- checkpoint deletion remains scoped to the dedicated consumer and scoped N4 source partitions
- N5 downstream and user-layer guards remain present
- rollback does not delete N4/N3/downstream business facts

## Validation

Completed:

```text
PYTHONPATH=src python3 -m unittest tests/test_v3_20260616_stale_n5_formal_amount_chain_rollback_guard.py
python3 -m compileall tests/test_v3_20260616_stale_n5_formal_amount_chain_rollback_guard.py
inline python rollback static assertions
python3 -m json.tool docs/V3_20260616_STALE_N5_FORMAL_AMOUNT_CHAIN_UNIT_BUG_ROLLBACK_CHECKPOINT_GUARD_REPAIR_REPORT.json >/dev/null
git diff --check
```

Results: `PASS`

## Forbidden Scope Proof

- rollback executed: `false`
- database written: `false`
- outbox consumed or updated: `false`
- inbox/checkpoint consumed or updated: `false`
- N4 modified: `false`
- N3 modified: `false`
- N5 execute run started: `false`
- N6 entered: `false`
- worker/scheduler started: `false`
- voice/mobile/sim/position/order/real trade touched: `false`
- old system touched: `false`

## Next Gate

Allowed next gate:

`V3_20260616_STALE_N5_FORMAL_AMOUNT_CHAIN_UNIT_BUG_ROLLBACK_FINAL_GATE_REVIEW_RETRY`

Prompt:

```text
layer_role=N5_action。

进入 V3_20260616_STALE_N5_FORMAL_AMOUNT_CHAIN_UNIT_BUG_ROLLBACK_FINAL_GATE_REVIEW_RETRY。

目标：只读复核已修复的 scoped N5 rollback SQL，确认 non-scoped N4 checkpoint refs 不再阻断，且 rollback 仍只删除 v3_n5_action_replay_20260616_after_n4_trigger_price_repair_v1 及 consumer n5_action_consumer_v1_20260616_trigger_price_repair_replay 的 scoped N4 inbox/checkpoint。

读取：
- docs/V3_20260616_STALE_N5_FORMAL_AMOUNT_CHAIN_UNIT_BUG_ROLLBACK_CHECKPOINT_GUARD_REPAIR_REPORT.md/json
- sql/V3_20260616_n5_action_after_n4_trigger_price_repair_rollback.sql

确认：
- non_scoped_n4_checkpoint_refs=3431 为 preserved/non-blocking
- N5 outbox delivered/delivering=0
- N5 downstream refs=0
- N6/user/sim/voice/mobile/position/order/trade refs=0
- rollback SQL hard-fail before first DELETE/UPDATE
- DELETE scope only scoped N5 run and dedicated consumer N4 inbox/checkpoint
- 不删除 N4/N3 facts，不更新 N4 outbox status

禁止 execute rollback、禁止写数据库、禁止进入 N6、禁止启动 worker/scheduler。

输出 PASS / BLOCKED、rollback risk、allowed rollback command。
```
