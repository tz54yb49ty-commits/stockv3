# N5 20260608 Until 15:00 Scoped Coverage Repair Additive Post Review

- result: POST_REVIEW_PASS
- source_trigger_run_id: trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry
- action_run_id: action_consumer_execute_20260608_until_1500_scoped_coverage_repair_additive__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry
- consumer_name: n5_action_consumer_v1_until_1500_scoped_coverage_repair_additive
- common_action_run.status: passed
- P0/P1/P2: 0/0/0
- deterministic metric join coverage: 556/556

## Rows

- common_action_run: 1
- common_action_quality_item: 0
- stock_action_fact: 412
- index_action_fact: 60
- board_action_fact: 84
- common_action_event: 556
- common_event_outbox: 556
- common_event_inbox: 556
- common_event_consumer_checkpoint: 541
- common_position_state: 0
- common_position_event: 0

## Event Distribution

- ActionExecuted: 7
- ActionBlocked: 549
- ActionEligible: 0
- ActionSkipped: 0

## Blocked Reason

- price_confirmation_failed: 535
- amount_confirmation_failed: 14
- <none>: 7

## Boundary

- N4 outbox remains TriggerMatched pending=556.
- N5 outbox remains pending and was not consumed.
- N6/user/voice/mobile/sim/position/order/trade refs for this action_run_id are 0.
- Worker was not started.
- Rollback SQL is present and was not executed.
