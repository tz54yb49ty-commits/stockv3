# V3 20260612 Stale N5 Action Mark Run Rollback Final Gate Review Retry

Result: `PASS`

This retry gate remained read-only. It did not execute rollback, did not write database rows, did not consume or update outbox/inbox/checkpoint, and did not enter N4/N5/N6/voice/mobile/sim/trade.

## Final Gate Findings

The rollback checkpoint guard repair is registered as `REPAIR_PASS`.

The previous blocker has been removed:

- Removed guard: non-scoped `common_event_consumer_checkpoint` refs for the preserved N4 source partitions.
- Non-scoped N4 checkpoints now do not block scoped stale N5 rollback.
- Non-scoped N4 checkpoints are not deleted.
- Checkpoint delete scope remains limited to `n5_action_consumer_v1` and the scoped N4 source run.

This gate allows entering the N5_action rollback user confirmation point. Runtime control still must not execute the rollback.

## Live N5 Scope Proof

- `common_action_run=1`
- `common_action_quality_item=4405`
- `stock_action_fact=33`
- `index_action_fact=0`
- `board_action_fact=10`
- `common_action_event=43`
- `common_event_outbox_n5=43`
- `common_event_ledger_n5=0`
- `common_event_inbox_n5_consumer_for_n4_source=4454`
- `common_event_checkpoint_n5_consumer_for_n4_source_partitions=2082`

## Live Rollback Safety Proof

- `n5_outbox_delivered_delivering=0`
- `n5_downstream_inbox_refs=0`
- `n5_downstream_checkpoint_refs=0`
- `non_scoped_consumer_inbox_refs_for_n4_source=0`
- `non_scoped_consumer_checkpoint_refs_for_n4_source_preserved_not_guarded=6279`
- N6/user/sim/voice/mobile/position refs: `0` for existing checked tables; optional legacy projection tables are absent.

## N4 Preservation Proof

N4 is preserved and not part of this rollback scope:

- `common_trigger_run=1`
- `common_trigger_match=4454`
- `common_trigger_state=4454`
- `common_event_outbox_n4=4454`
- N4 outbox delivered/delivering: `0`

## Rollback SQL Proof

SQL: `sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql`

- Hard-fail guard exists before first `DELETE/UPDATE`.
- Non-scoped checkpoint hard-fail guard is absent.
- Non-scoped checkpoint delete is absent.
- Scoped checkpoint delete for `n5_action_consumer_v1` is present.
- No `DROP`, `TRUNCATE`, or `CASCADE`.
- No delete from `common_trigger*`.
- No delete from `*_action_confirmation_projection_metric`.
- No delete from `common_market_data*`.

## Allowed Rollback Command Draft

Allowed only in `layer_role=N5_action` after explicit user confirmation:

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

1. Enter `V3_20260612_STALE_N5_ACTION_MARK_RUN_ROLLBACK_EXECUTE_GATE` in `N5_action`.
2. If user confirms, execute only the scoped stale N5 rollback SQL.
3. Run rollback post-review and confirm stale N5 refs are gone.
4. Refresh N3 repair SQL to allow reviewed N4 refs while still blocking N5/N6/user refs.

## Next Prompt

```text
layer_role=N5_action。

进入 V3_20260612_STALE_N5_ACTION_MARK_RUN_ROLLBACK_EXECUTE_GATE。

目标：按 runtime_control final gate PASS 的 scoped rollback command，回滚 20260612 stale N5 action_mark run：v3_n5_action_consumer_20260612_from_n4_action_confirmation_metric_after_n3_writer_v1。只允许执行 sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql；删除范围仅 stale N5 run 的 action facts/events/outbox/quality/run，以及 n5_action_consumer_v1 对 scoped N4 source run 的 inbox/checkpoint。必须保留 N4 run 和 N3 projection run，不消费/update N4 outbox status，不进入 N6/voice/mobile/sim/position/trade。执行后生成 execute report 与 post-review proof。
```
