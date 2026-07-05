# N4 Projection Matcher 20260608 v13 index-all until 0952 Rollback Report

- result: ROLLBACK_PASS
- layer_role: N4_trigger
- stage: N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_0952_ROLLBACK_USER_CONFIRMATION_GATE
- generated_at: 2026-06-08T14:23:15+08:00
- target_run_id: trigger_projection_matcher_execute_20260608_v13_index_all_until_0952
- rollback_sql: `sql/N4_projection_matcher_20260608_v13_index_all_until_0952_v4_breach_repair_rollback.sql`

## Execution

The plain `psql` executable was not available in the shell `PATH`; that first shell attempt failed before any database connection or SQL execution.

The rollback was executed with the PostgreSQL 16 `psql` binary and the same scoped rollback SQL:

```bash
/opt/homebrew/Cellar/postgresql@16/16.14/bin/psql "host=127.0.0.1 port=5432 dbname=ashare_v3 user=ashare_v3_user" \
  -v ON_ERROR_STOP=1 \
  -f sql/N4_projection_matcher_20260608_v13_index_all_until_0952_v4_breach_repair_rollback.sql
```

SQL exit code: `0`

Rollback notice:

```text
N4 projection matcher rollback completed for trigger_projection_matcher_execute_20260608_v13_index_all_until_0952,
outbox=3920, match=3920, state=3920, quality=10, inbox=2155, checkpoint=2155, run=1
```

## Deleted Rows

| Scope | Deleted |
|---|---:|
| common_event_outbox | 3920 |
| common_trigger_match | 3920 |
| common_trigger_state | 3920 |
| common_trigger_quality_item | 10 |
| common_event_inbox | 2155 |
| common_event_consumer_checkpoint | 2155 |
| common_trigger_run | 1 |

## Post-Check

Target run scoped rows are all zero:

| Scope | Remaining |
|---|---:|
| common_trigger_run | 0 |
| common_trigger_quality_item | 0 |
| common_trigger_match | 0 |
| common_trigger_state | 0 |
| common_event_outbox | 0 |
| common_event_inbox | 0 |
| common_event_consumer_checkpoint | 0 |

## Upstream Preserved

N3 MarketSnapshotUpdated outbox remains pending:

| Event | Status | Count |
|---|---|---:|
| MarketSnapshotUpdated | pending | 2155 |

N3 snapshot facts remain present:

| Table | Rows |
|---|---:|
| stock_realtime_daily_snapshot | 1945 |
| index_realtime_daily_snapshot | 83 |
| board_realtime_daily_snapshot | 127 |

N3 projection facts remain present:

| Table | Rows |
|---|---:|
| stock_realtime_projection_metric | 1945 |
| index_realtime_projection_metric | 83 |
| board_realtime_projection_metric | 127 |

N3 run status remains:

| Run | Status | P0 | P1 | P2 |
|---|---|---:|---:|---:|
| realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute | passed | 0 | 0 | 0 |
| realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute | passed | 0 | 4 | 0 |

N1/N2/N3 facts were not touched by the rollback.

## Downstream Clean

| Scope | Refs |
|---|---:|
| common_action_run | 0 |
| common_action_event | 0 |
| user_projection_run | 0 |
| user_signal_projection | 0 |
| user_signal_card | 0 |
| user_notification_queue | 0 |
| user_sim_order | 0 |
| user_sim_position | 0 |
| user_sim_trade | 0 |

## Rollback SQL Static Check

- `RAISE EXCEPTION` before first `DELETE FROM`: true
- `TRUNCATE`: false
- `DROP TABLE`: false
- `CASCADE`: false
- Guards include outbox, inbox, checkpoint, N5 action refs, N6 user refs, and user sim refs.

## Forbidden Scope Proof

- repair_executed=false
- n4_matcher_rerun=false
- n5_entered=false
- n6_entered=false
- n3_outbox_status_updated=false
- worker_started=false
- delivery/push/voice/mobile=false
- sim/position/pnl/real_trade=false
- proposal/order/trade=false
- old_system_touched=false

## Next Gate

Allowed to return to runtime_control for:

```text
N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_0952_ROLLBACK_POST_REVIEW_GATE
```
