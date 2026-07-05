# V3 20260612 N3/N4/N5 Realtime Replay Closeout Registration

- result: `CLOSEOUT_PASS`
- generated_at: `2026-06-13T15:44:45.944196+08:00`

## Run IDs

- source_condition_run_id: `condition_layer_20260611_source_20260611_for_20260612_v1`
- trigger_context_run_id: `trigger_context_snapshot_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`
- n3_today_1m_backfill_run_id: `v3_n3_minute_bar_1m_backfill_20260612_full_scope_v1`
- n3_previous_day_1m_backfill_run_id: `v3_n3_previous_day_minute_bar_1m_backfill_20260611_for_20260612_full_scope_v1`
- n3_full_day_metric_run_id: `v3_n3_action_confirmation_metric_20260612_full_day_replay_v1`
- n4_full_day_trigger_replay_run_id: `v3_n4_trigger_replay_20260612_after_n3_full_day_metric_v1`
- n5_full_day_action_replay_run_id: `v3_n5_action_replay_20260612_after_n4_full_day_trigger_v1`
- n5_consumer_name: `v3_n5_action_replay_20260612_full_day_consumer_v1`

## Row Count Registry

- N3 today 1m rows stock/index/board/total: `449280/19440/30480/499200`
- N3 previous-day 1m rows stock/index/board/total: `449280/19440/30480/499200`
- N3 metric rows stock/index/board/total: `449280/19440/30480/499200`; ready/not_ready=`499200/0`
- N4 trigger rows state/match/outbox: `24255/24255/24255`; pending/delivered=`24255/0`
- N5 action facts stock/index/board: `21075/686/1307`; events/outbox=`23068/23068`
- N5 outbox by event type: `[('ActionBlocked', 18155), ('ActionExecuted', 4913)]`
- N5 action states: `[('blocked', 18155), ('executed', 4913)]`

## 603259 Proof

- N3 10:56 metric ready: `True`, quality=`passed`, current_d_virtual_amount=`2222502455.04`, previous_d_amount=`5540197.469`
- N3 10:56 buy flags 120/30/5/1 price + 5/1 amount: `[True, True, True, True, True, True]`
- N4 TriggerMatched before 10:56 count sample: `3`; at 10:56 count=`0`
- N5 actions for 603259: `[(datetime.datetime(2026, 6, 12, 9, 31, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'ActionExecuted', 'executed', '30m_volume'), (datetime.datetime(2026, 6, 12, 10, 0, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'ActionExecuted', 'executed', '30m_volume'), (datetime.datetime(2026, 6, 12, 10, 34, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'ActionBlocked', 'blocked', None), (datetime.datetime(2026, 6, 12, 11, 27, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'ActionExecuted', 'executed', '30m_volume'), (datetime.datetime(2026, 6, 12, 13, 1, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'ActionExecuted', 'executed', '30m_volume'), (datetime.datetime(2026, 6, 12, 13, 13, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'ActionBlocked', 'blocked', None), (datetime.datetime(2026, 6, 12, 14, 5, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'ActionBlocked', 'blocked', None), (datetime.datetime(2026, 6, 12, 14, 9, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'ActionBlocked', 'blocked', None), (datetime.datetime(2026, 6, 12, 14, 15, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'ActionBlocked', 'blocked', None), (datetime.datetime(2026, 6, 12, 14, 17, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'ActionBlocked', 'blocked', None), (datetime.datetime(2026, 6, 12, 14, 37, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'ActionBlocked', 'blocked', None), (datetime.datetime(2026, 6, 12, 14, 52, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'ActionExecuted', 'executed', '30m_volume')]`

## Next-Trade-Day Guard

- metric coverage guard result: `BLOCKED`
- blocked_reason: `n3_metric_coverage_missing_for_n4_context`
- missing identity count/sample: `2` / `['index:BJ:899050', 'index:BJ:899601']`

## Rollback Registry

- n3_today_1m_backfill: `sql/V3_20260612_n3_full_day_1m_backfill_rollback.sql`
- n3_previous_day_1m_backfill: `sql/V3_20260612_n3_previous_day_full_scope_1m_backfill_rollback.sql`
- n3_full_day_metric: `sql/V3_20260612_n3_full_day_action_confirmation_metric_rollback.sql`
- n4_full_day_trigger_replay: `sql/V3_20260612_n4_full_day_trigger_replay_rollback.sql`
- n5_full_day_action_replay: `sql/V3_20260612_n5_full_day_action_replay_rollback.sql`
- rollback_executed: `False`

## Forbidden Scope

- old_system_read: `False`
- scheduler_started_or_modified_in_closeout: `False`
- manual_wrapper_execute_in_closeout: `False`
- n6_entered: `False`
- voice_mobile_sim_position_order_trade_touched: `False`
- rollback_executed: `False`

## Residual Notes

- This replay is V3-only and does not use the old target-machine database as truth.
- N4 full-day replay persisted activation TriggerMatched events; full historical invalidation TriggerStateChanged persistence remains a separate optional replay if needed.
- The next-trade-day metric coverage guard is active before N4; current full-day guard still reports two missing BJ index identities, so production should either add a reviewed BJ index data policy or keep blocking visibly instead of silently continuing.
- N5 ActionExecuted is an action-confirmation fact only; N6/user notification, voice, mobile, sim, order, position, and real trade were not entered.

## Validation

- targeted_tests: `PASS: PYTHONPATH=src:scripts python3 -m unittest tests.test_v3_20260612_full_day_replay_plan tests.test_v3_realtime_engine_once (17 tests OK)`
- compileall: `PASS: targeted scripts/src/tests compileall`
- json_parse: `PASS: closeout JSON parse and key execute reports loaded during verification`
- rollback_static_check: `PASS: hard-fail before first DELETE and no DROP/TRUNCATE/CASCADE for registered rollback SQL`
- git_diff_check: `PASS`
