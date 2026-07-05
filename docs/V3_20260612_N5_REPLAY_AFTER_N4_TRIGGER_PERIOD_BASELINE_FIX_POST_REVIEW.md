# V3 20260612 N5 Replay After N4 Trigger Period Baseline Fix Post Review

Result: `POST_REVIEW_PASS`

```text
action_run_id=v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1
source_trigger_run_id=v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1
consumer_name=v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_consumer_v1
run_status=passed P0/P1/P2=0/0/0
row_counts={'common_action_run': 1, 'common_action_quality_item': 0, 'stock_action_fact': 965, 'index_action_fact': 154, 'board_action_fact': 68, 'common_action_event': 1187, 'n5_common_event_outbox': 1187, 'consumer_inbox': 1187, 'consumer_checkpoint': 235}
action_events={'ActionBlocked': 911, 'ActionExecuted': 276}
formal_period_payload_proof={'fabricated_formal_period_count': 0, 'fabricated_sample': [], 'hint_payload_bad_count': 0, 'hint_bad_sample': [], 'hint_count': 1187, 'ordinary_count': 0, 'trigger_period_distribution': {'30m': 1187}}
n4_outbox_delivered_or_delivering=0
N6/user refs=0
```

Boundary: N4 outbox status was not updated; N6/user/voice/mobile/sim/position/order/real trade were not touched.
