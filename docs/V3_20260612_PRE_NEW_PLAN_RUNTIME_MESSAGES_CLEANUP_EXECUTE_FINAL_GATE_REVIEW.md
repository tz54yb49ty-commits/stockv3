# V3 20260612 Pre-New-Plan Runtime Messages Cleanup Execute Final Gate Review

Result: `PASS`

This is a read-only final gate review. It did not execute cleanup, did not write the database, did not execute rollback, did not start or modify scheduler, did not manually run wrapper/N3/N4/N5, did not consume or update outbox/inbox/checkpoint, and did not enter N6/voice/mobile/sim/trade.

## Final Gate Findings

Required upstream artifacts are present and parse:

- cleanup contract: `CONTRACT_PASS`
- cleanup preflight: `DRY_RUN_PREFLIGHT_PASS`
- scheduler stop report: `STOP_PASS`

Scheduler proof:

- label: `com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll`
- `launchctl print` exit code: `113`
- state: `not_loaded`
- active wrapper/child process count: `0`

## Live Reference Proof

N6/user refs are clean:

- `user_projection_run=0`
- `user_signal_projection=0`
- `user_signal_card=0`
- `user_notification_queue=0`

N6 virtual / user sim refs are clean:

- `n6_virtual_order=0`
- `n6_virtual_trade=0`
- `n6_virtual_position=0`
- `n6_virtual_position_event=0`
- `n6_virtual_pnl_snapshot=0`
- `user_sim_order=0`
- `user_sim_trade=0`
- `user_sim_position=0`

N5 scoped rows:

- `common_action_run=3`
- `common_action_quality_item=0`
- `stock_action_fact=2436`
- `index_action_fact=0`
- `board_action_fact=1`
- `common_action_event=2437`
- `common_event_outbox=2437`
- `common_event_inbox=2437`
- `common_event_consumer_checkpoint=2402`

N5 outbox downstream refs:

- `inbox=0`
- `checkpoint=0`

N4 scoped rows:

- `common_trigger_run=4`
- `common_trigger_quality_item=36`
- `common_trigger_state=4865`
- `common_trigger_match=3249`
- `common_event_outbox=4865`
- `common_event_inbox=8328`
- `common_event_consumer_checkpoint=8328`
- downstream N5 action run refs before cleanup: `3`

N3 derived scope:

- standard B1 outbox runs: `11`
- trace-aligned B2 runs: `4`
- standard quality rows: `110`
- trace B2 quality rows: `28`
- standard stock/index/board snapshots: `20592/913/1397`
- `MarketSnapshotUpdated` outbox rows: `22902`
- trace B2 stock/index/board projection rows: `7488/332/508`
- downstream inbox/checkpoint refs from scoped N3 standard outbox: `8328/8328`

The N3 downstream refs are expected at this stage because N4 inbox/checkpoint rows still exist. The cleanup SQL deletes N5 first, then N4, then asserts these N3 refs are zero before deleting N3 derived rows.

## Cleanup SQL Proof

Cleanup SQL:

`sql/V3_20260612_pre_new_plan_runtime_messages_cleanup.sql`

Proof:

- default hard-fail exists before first executable mutation
- requires `SET LOCAL ashare_v3.allow_v3_20260612_pre_new_plan_cleanup = 'true'`
- backs up rows into `common_runtime_cleanup_backup`
- deletes in reverse dependency order: `N5 -> N4 -> N3 derived`
- guards N6/user refs, N6 virtual/user sim refs, N5 outbox downstream refs, and expected scoped counts
- no `DROP`, `TRUNCATE`, or `CASCADE`
- no preserved source scope tokens: minute bar, previous-day preload, subscription, pull-plan, N1/N2 condition tables, old system

## Rollback Proof

Rollback SQL:

`sql/V3_20260612_pre_new_plan_runtime_messages_cleanup_rollback.sql`

Proof:

- default hard-fail exists before first restore mutation
- requires `SET LOCAL ashare_v3.allow_v3_20260612_pre_new_plan_cleanup_rollback = 'true'`
- restores from `common_runtime_cleanup_backup`
- no `DROP`, `TRUNCATE`, or `CASCADE`

## Allowed Cleanup Command Draft

This final gate allows entering the cleanup user confirmation point. It does not execute cleanup.

After explicit user confirmation, the scoped cleanup command shape is:

```bash
PYTHONPATH=src:scripts python3 - <<'PY'
from pathlib import Path
import psycopg

sql_path = Path("sql/V3_20260612_pre_new_plan_runtime_messages_cleanup.sql")
sql = sql_path.read_text()
needle = "    RAISE EXCEPTION 'cleanup blocked by default; remove this line only in an approved execute gate after refreshing live refs';\n"
if needle not in sql:
    raise SystemExit("default hard-fail line not found or already removed")
sql = sql.replace(needle, "", 1)

with psycopg.connect("dbname=ashare_v3 user=ashare_v3_user host=127.0.0.1 port=5432") as conn:
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SET LOCAL ashare_v3.allow_v3_20260612_pre_new_plan_cleanup = 'true'")
            cur.execute(sql)
PY
```

Before running it, the execute gate must refresh live refs again.

## Write Risk

Risk level: `high_but_scoped`

Reason: the cleanup deletes scoped N3/N4/N5 runtime derived rows after backing them up. It does not delete raw/source facts.

## Forbidden Scope Proof

This final gate did not:

- execute cleanup
- write database rows
- execute rollback
- start or modify scheduler
- manually execute wrapper/N3/N4/N5
- consume or update outbox/inbox/checkpoint
- enter N6
- touch voice/mobile/sim/position/PnL/real trade
- touch the old system

Decision:

`allow_enter_cleanup_user_confirmation_point=true`

Next gate:

```text
layer_role=runtime_control。

进入 V3_20260612_PRE_NEW_PLAN_RUNTIME_MESSAGES_CLEANUP_EXECUTE_GATE。

目标：
在 final gate PASS 后，按 approved scoped cleanup command 执行 20260612 新方案前 N3/N4/N5 derived runtime messages cleanup。必须在同一事务内设置 allow flag，只删除 SQL 中 scoped rows，备份到 common_runtime_cleanup_backup，不启动 scheduler，不手动执行 wrapper/N3/N4/N5，不进入 N6/voice/mobile/sim/trade。执行后复核 target rows=0、preserved source facts untouched、rollback registry safe，并生成 cleanup execute/post-review artifacts。
```
