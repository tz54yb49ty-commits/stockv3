# V3 20260612 Stale N5 Action Mark Rollback Final Gate Review Including Realtime Engine Consumer

Result: `PASS`

This runtime-control gate was read-only. It did not execute rollback, did not write database rows, did not restart the scheduler, did not manually execute wrapper/N3/N4/N5, did not consume or update outbox/inbox/checkpoint, and did not enter N6/voice/mobile/sim/position/trade.

## Final Gate Findings

The V3 realtime engine scheduler is stopped:

- label: `com.ashare-v3.v3-realtime-engine`
- launchctl state: `not_loaded`
- launchctl print exit code: `113`
- wrapper/child process count: `0`

The rollback scope repair is registered as `REPAIR_PASS`.

Reviewed stale consumers now covered by the rollback SQL:

- `n5_action_consumer_v1`
- `v3_realtime_engine_n5_consumer_20260612`

No non-stale consumer inbox refs remain for the scoped N4 source.

## Live Stale N5 Scope Proof

- `common_action_run=1`
- `common_action_quality_item=0`
- `stock_action_fact=33`
- `index_action_fact=0`
- `board_action_fact=10`
- `common_action_event=43`
- N5 outbox `43`, pending `43`, delivered/delivering `0`
- N5 downstream inbox/checkpoint refs: `0/0`
- reviewed stale consumers inbox/checkpoint: `49/43`
- non-stale consumers inbox refs: `0`

Consumer detail:

- `v3_realtime_engine_n5_consumer_20260612`: inbox refs `49`, received at `2026-06-13 09:59:11.293845+08`

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
- Both reviewed stale consumers are declared.
- N4-source inbox delete uses the stale consumer array.
- N4-source checkpoint delete uses the stale consumer array.
- Non-stale N4-source inbox guard is present.
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

Keep `com.ashare-v3.v3-realtime-engine` stopped until rollback post-review is complete.

## Forbidden Scope Proof

- Rollback executed: `false`
- Database written: `false`
- Scheduler started or modified: `false`
- Wrapper manually executed: `false`
- Outbox consumed or updated: `false`
- Inbox/checkpoint consumed or updated: `false`
- N4 executed or modified: `false`
- N5 executed: `false`
- N6 entered: `false`
- Voice/mobile/sim/position/trade touched: `false`
- Old system modified: `false`

## Rollback 后路线

1. Enter `V3_20260612_STALE_N5_ACTION_MARK_RUN_ROLLBACK_EXECUTE_GATE_INCLUDE_REALTIME_ENGINE_CONSUMER` in `N5_action`.
2. If user confirms, execute only the scoped stale N5 rollback SQL.
3. Run rollback post-review and confirm stale N5 refs are gone.
4. Refresh N3 repair SQL to allow reviewed N4 refs while still blocking N5/N6/user refs.

## Next Prompt

```text
layer_role=N5_action。

进入 V3_20260612_STALE_N5_ACTION_MARK_RUN_ROLLBACK_EXECUTE_GATE_INCLUDE_REALTIME_ENGINE_CONSUMER。

目标：在 V3 realtime engine scheduler 已 stop/not_loaded 后，按 runtime_control final gate PASS 的 scoped rollback SQL，完成 stale N5 action_mark run 清理。只允许执行 sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql；删除范围仅 stale N5 run 的 action facts/events/outbox/quality/run，以及 reviewed stale consumers n5_action_consumer_v1 / v3_realtime_engine_n5_consumer_20260612 对 scoped N4 source 的 inbox/checkpoint。必须保留 N4 run 和 N3 projection run，不消费/update N4 outbox status，不重启 scheduler，不进入 N6/voice/mobile/sim/position/trade。执行后生成 execute report 与 post-review proof。
```
