# V3 20260612 Stale N5 Action Mark Run Rollback Final Gate Review

Result: `BLOCKED`

This gate did not execute rollback, did not write database rows, did not consume or update outbox/inbox/checkpoint, and did not enter N4/N5/N6/voice/mobile/sim/trade.

## Final Gate Findings

The stale N5 run is real and scoped:

- N5 run: `v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1`
- Source N4 run: `v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`
- Consumer: `n5_action_consumer_v1`
- N5 outbox: `43`
- N5 outbox delivered/delivering: `0`
- N5 downstream inbox/checkpoint refs: `0/0`
- N6/user/sim/voice/mobile/position refs: `0`

But the current rollback SQL cannot be approved for execution yet. Live read-only proof shows:

- `non_scoped_consumer_checkpoint_refs_for_n4_source=6279`

The rollback SQL currently hard-fails on those non-scoped consumer checkpoint refs for the same preserved N4 source partitions. Because the approved policy is to preserve N4 and delete only the stale N5 run plus `n5_action_consumer_v1` inbox/checkpoint rows, these non-scoped N4 checkpoint refs should not be deleted and should not block after reviewed guard repair. With the current SQL, rollback execution would fail before the first `DELETE`.

## Live N5 Scope Proof

- `common_action_run=1`
- `common_action_quality_item=4405`
- `stock_action_fact=33`
- `index_action_fact=0`
- `board_action_fact=10`
- `common_action_event=43`
- `common_event_outbox_n5=43`
- `common_event_ledger_n5=0`
- `common_event_inbox_n5_consumer_for_scoped_n4_source=4454`

## Live Rollback Safety Proof

- `n5_outbox_delivered_delivering=0`
- `n5_downstream_inbox_refs=0`
- `n5_downstream_checkpoint_refs=0`
- `non_scoped_consumer_inbox_refs_for_n4_source=0`
- `non_scoped_consumer_checkpoint_refs_for_n4_source=6279`
- N6/user/sim/voice/mobile/position refs: `0` for existing checked tables; optional legacy projection tables are absent.

## N4 Preservation Proof

N4 is preserved and must not be rolled back by this route:

- `common_trigger_run=1`
- `common_trigger_match=4454`
- `common_trigger_state=4454`
- `common_event_outbox_n4=4454`
- N4 outbox delivered/delivering: `0`

The rollback SQL does not delete N4 trigger rows or N3 market-data rows.

## Rollback SQL Proof

SQL: `sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql`

- Hard-fail guard exists before first `DELETE/UPDATE`.
- No `DROP`, `TRUNCATE`, or `CASCADE`.
- No delete from `common_trigger*`.
- No delete from `*_action_confirmation_projection_metric`.
- No delete from `common_market_data*`.
- Declared delete scope is stale N5 action run rows and `n5_action_consumer_v1` inbox/checkpoint rows for the scoped N4 source run.

## Allowed Rollback Command Draft

No rollback command is allowed by this gate.

The command draft must remain blocked until the checkpoint guard is repaired and this final gate is repeated:

```bash
psql "$ASHARE_V3_RUNTIME_DSN" -v ON_ERROR_STOP=1 \
  -f sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql
```

## Forbidden Scope Proof

- Rollback executed: `false`
- Database written: `false`
- Outbox consumed or updated: `false`
- Inbox/checkpoint consumed or updated: `false`
- N4 executed or modified: `false`
- N5 executed: `false`
- N6 entered: `false`
- Voice/mobile/sim/position/trade touched: `false`
- Old system modified: `false`

## Rollback 后路线

1. Enter `V3_20260612_STALE_N5_ACTION_MARK_ROLLBACK_CHECKPOINT_GUARD_REPAIR_GATE` in `N5_action`.
2. Repair rollback SQL so non-scoped consumer checkpoints on preserved N4 source partitions do not block stale N5 scoped rollback and are not deleted.
3. Repeat runtime_control rollback final gate.
4. After stale N5 rollback succeeds, refresh N3 repair SQL to allow reviewed N4 refs while still blocking N5/N6/user refs.

## Next Prompt

```text
layer_role=N5_action。

进入 V3_20260612_STALE_N5_ACTION_MARK_ROLLBACK_CHECKPOINT_GUARD_REPAIR_GATE。

目标：修复 stale N5 action_mark rollback SQL 的 checkpoint guard 过宽问题。当前 final gate live proof 显示 N5 outbox delivered/delivering=0、N5 downstream inbox/checkpoint refs=0、N6/user refs=0，但 rollback SQL 会因 non_scoped_consumer_checkpoint_refs_for_n4_source=6279 阻断。N4 run 保留不回滚，因此非本 N5 consumer 的 N4 checkpoint refs 不应阻断 N5 scoped rollback，也不得被删除。请只改 rollback SQL/tests/report：保留 hard-fail before first DELETE；删除范围仍仅 stale N5 run + n5_action_consumer_v1 对 scoped N4 source 的 inbox/checkpoint；继续阻断 N5 delivered/delivering、N5 downstream refs、N6/user/sim/voice/mobile refs；不执行 rollback、不写 DB、不进入 N4/N5/N6。
```
