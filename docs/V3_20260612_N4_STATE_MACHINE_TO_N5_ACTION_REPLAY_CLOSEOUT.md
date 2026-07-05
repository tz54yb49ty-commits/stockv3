# V3 20260612 N4 State Machine -> N5 Action Replay Closeout

- result: `CLOSEOUT_PASS`
- N4 run: `v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3` status `passed`
- N4 outbox: `TriggerMatched=25282`, `TriggerPendingMarketData=4`, `TriggerStateChanged=19720`
- N5 run: `v3_n5_action_replay_20260612_after_n4_state_machine_v3` status `passed`
- N5 input: `TriggerMatched` only, read `25282`
- N5 facts stock/index/board: `22223/975/1829`
- N5 events: `{'ActionBlocked': 911, 'ActionExecuted': 24116}`
- N5 action_mark: `{'30m_shrink': 1612, '30m_volume': 13303, 'normal': 9201, 'None': 911}`
- 603259 10:56: `[{'action_state': 'executed', 'confirmation_status': 'passed', 'action_mark': '30m_volume', 'signal_type': 'B_BUY', 'condition_key': 'BUY:Q,M,W,D', 'trigger_time': '2026-06-12 10:56:00+08:00'}]`
- N6/user refs: projection/card/notification `0/0/0`
- position refs: state/event `0/0`

## Rollback Registry
- N4: `sql/V3_20260612_n4_full_day_trigger_replay_rollback.sql`
- N5: `sql/V3_20260612_n5_action_replay_after_n4_state_machine_v3_rollback.sql`

## Residual Notes
- N4 persisted TriggerMatched=25282 and N5 consumed only TriggerMatched.
- N4 state table has 89275 rows; N4 TriggerStateChanged outbox has 19720 pending rows due current event_id/dedup compaction. This does not affect N5 TriggerMatched-only replay, but should be reviewed before using state-change broadcast counts as a full audit stream.
- N5 execute report JSON is large because it embeds sampled dry-run plan and trace payloads; future reports should compact output for full-day replay.
