# V3 20260612 Previous Day Same Window Amount Repair Execute Final Gate Review After N4 Ref Guard Refresh

Result: `PASS`

This runtime-control gate was read-only. It did not execute SQL, did not write database rows, did not restart the scheduler, did not execute N4/N5/N6, and did not consume or update outbox/inbox/checkpoint.

## Final Gate Findings

The N3 repair is ready to enter the `N3_market_data` execute confirmation point.

Prerequisites are satisfied:

- N3 repair report: `REPAIR_PASS`
- stale N5 action_mark rollback post-review: `POST_REVIEW_PASS`
- scheduler: `com.ashare-v3.v3-realtime-engine` remains `not_loaded`
- target projection rows: stock/index/board/total `62/0/38/100`
- payload coverage: `previous_day_same_window_amount=100/100`

## Live Schema And Row Proof

`previous_day_same_window_amount` is still absent from all three metric tables:

- `stock_action_confirmation_projection_metric=0`
- `index_action_confirmation_projection_metric=0`
- `board_action_confirmation_projection_metric=0`

Target projection rows exist:

- stock `62`
- index `0`
- board `38`
- total `100`

The target `common_market_data_run` exists and has no blocked downstream flags.

## Ref Proof

Reviewed N4 refs are present and allowed:

- N4 outbox refs `4454`
- `common_trigger_match=4454`
- `common_trigger_run=1`
- `common_trigger_state=4454`

Blocked ref classes are currently zero:

- non-reviewed outbox refs `0`
- inbox/checkpoint refs `0/0`
- N5 action refs `0`
- N6/user/sim/virtual refs `0`

## SQL Proof

SQL: `sql/V3_20260612_realtime_virtual_metric_previous_day_same_window_amount_repair.sql`

- Default hard-fail exists before first `ALTER/UPDATE`.
- Requires session flag: `ashare_v3.allow_v3_20260612_previous_day_same_window_amount_repair=true`
- Reviewed N4 refs are explicitly allowed and preserved.
- N5/N6/user/sim/virtual refs remain hard-fail blockers.
- No `DROP`, `TRUNCATE`, or `CASCADE`.
- Backfill assertions require stock/index/board `62/0/38`.

Allowed write scope after N3 confirmation:

- additive column `previous_day_same_window_amount` on stock/index/board metric tables
- scoped backfill for the target projection run only
- trace_json repair marker append

## Allowed Execute Command Draft

Allowed only in `layer_role=N3_market_data` after explicit user confirmation:

```bash
psql "$ASHARE_V3_RUNTIME_DSN" -v ON_ERROR_STOP=1 <<'SQL'
SET ashare_v3.allow_v3_20260612_previous_day_same_window_amount_repair = 'true';
\i sql/V3_20260612_realtime_virtual_metric_previous_day_same_window_amount_repair.sql
SQL
```

Keep `com.ashare-v3.v3-realtime-engine` stopped until N3 repair post-review and N5 replay readiness are complete.

## Forbidden Scope Proof

- SQL executed: `false`
- Database written: `false`
- Scheduler restarted or modified: `false`
- N4/N5/N6 executed: `false`
- Outbox consumed or updated: `false`
- Inbox/checkpoint consumed or updated: `false`
- Voice/mobile/sim/position/order/trade touched: `false`
- Old system modified: `false`

## Next Prompt

```text
layer_role=N3_market_data。

进入 V3_20260612_PREVIOUS_DAY_SAME_WINDOW_AMOUNT_REPAIR_EXECUTE_GATE_AFTER_N4_REF_GUARD_REFRESH。

目标：在 runtime_control final gate PASS 后，执行 scoped previous_day_same_window_amount additive schema/backfill repair SQL。只允许执行 sql/V3_20260612_realtime_virtual_metric_previous_day_same_window_amount_repair.sql，并在同一 psql session 先设置 SET ashare_v3.allow_v3_20260612_previous_day_same_window_amount_repair='true'。写入范围仅三张 action_confirmation_projection_metric 表的 additive column 与 target projection_run_id scoped backfill；保留 N4 run/outbox，不进入 N5/N6，不重启 scheduler，不消费/update outbox/inbox/checkpoint，不触碰 voice/mobile/sim/position/order/trade。执行后生成 execute report 与 post-review proof。
```
