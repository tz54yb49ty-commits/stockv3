# V3 20260612 N4/N5 30m Price Mark-Only Scoped Rollback Replay Closeout

- result: `CLOSEOUT_PASS`
- N4 v2 run: `v3_n4_trigger_replay_20260612_after_n3_full_day_metric_mark_only_fix_v2`
- N5 v2 run: `v3_n5_action_replay_20260612_after_n4_mark_only_fix_v2`
- N4 TriggerMatched rows: `25282`
- N4 mark distribution: `[{'mark': '30m_shrink', 'c': 2020}, {'mark': '30m_volume', 'c': 14061}, {'mark': 'normal', 'c': 9201}]`
- N5 action events/outbox: `25027/25027`
- N5 mark distribution: `[{'event_type': 'ActionBlocked', 'action_mark': None, 'c': 911}, {'event_type': 'ActionExecuted', 'action_mark': '30m_shrink', 'c': 1612}, {'event_type': 'ActionExecuted', 'action_mark': '30m_volume', 'c': 13303}, {'event_type': 'ActionExecuted', 'action_mark': 'normal', 'c': 9201}]`
- 603259 10:56 N4 proof: `[{'event_id': 'evt_fd95e91ee8f8a26ec1f6b62f32fa182b34cfd9bf', 'event_time': datetime.datetime(2026, 6, 12, 10, 56, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'condition_key': 'BUY:Q,M,W,D', 'mark': '30m_volume', 'metric_id': '685309'}]`
- 603259 10:56 N5 proof: `[{'event_id': 'evt_cb920d761e5bb14cab9c50ed86377acadedf2cbe', 'event_time': datetime.datetime(2026, 6, 12, 10, 56, tzinfo=zoneinfo.ZoneInfo(key='Asia/Shanghai')), 'event_type': 'ActionExecuted', 'action_state': 'executed', 'action_mark': '30m_volume', 'condition_key': 'BUY:Q,M,W,D'}]`
- N5 outbox delivered/delivering: `0`
- N6/user/position refs: `[{'table': 'user_signal_projection', 'exists': True, 'refs': 0}, {'table': 'user_signal_card', 'exists': True, 'refs': 0}, {'table': 'user_notification_queue', 'exists': True, 'refs': 0}, {'table': 'common_position_state', 'exists': True, 'refs': 0}, {'table': 'common_position_event', 'exists': True, 'refs': 0}]`
- old N4 v1 retained: `1`
- old N5 v1 rows: `0`
- old N5 v1 rollback report: `docs/V3_20260612_N5_FULL_DAY_ACTION_REPLAY_ROLLBACK_AFTER_30M_PRICE_MARK_ONLY_FIX_REPORT.json`
