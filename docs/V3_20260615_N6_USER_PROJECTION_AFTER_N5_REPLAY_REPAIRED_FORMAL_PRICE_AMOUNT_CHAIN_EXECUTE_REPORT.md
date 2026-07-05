# V3 20260615 N6 User Projection Execute Report

- gate: `V3_20260615_N6_USER_PROJECTION_AFTER_N5_REPLAY_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_EXECUTE_GATE`
- result: `EXECUTE_PASS`
- source_action_run_id: `v3_n5_action_replay_20260615_after_n4_repaired_formal_price_amount_chain_and_n3_coverage_repair_v1`
- projection_run_id: `v3_n6_user_projection_20260615_after_n5_replay_repaired_formal_price_amount_chain_and_n3_coverage_repair_v1`

## Execute Proof

- runner result: `EXECUTED`
- preflight_result: `PREFLIGHT_PASS`
- notification_queue_policy: `deferred`
- projection_run status: `passed`
- projection_run input/output: `1029/68`
- P0/P1/P2: `0/5/2`

## Row Count Proof

- user_projection_run: `1`
- user_signal_projection: `68`
- user_signal_card: `68`
- user_notification_queue: `0`

Projection distribution:

- ActionExecuted / executed / normal: `36`
- ActionExecuted / executed / 30m_volume: `32`

Card distribution:

- ActionExecuted / action_confirmed: `68`

## User Message Filter Proof

- include_event_types: `ActionEligible`, `ActionExecuted`
- source events: `1029`
- eligible user messages: `68`
- diagnosis-only ActionBlocked: `961`
- ActionBlocked rows were not projected as ordinary user messages.

## N5 Outbox Unchanged Proof

- ActionBlocked pending: `961`
- ActionExecuted pending: `68`
- common_event_inbox rows for source_run_id: `0`
- common_event_consumer_checkpoint rows for source_layer=N5_action: `0`

## Rollback Safety

- rollback SQL: `sql/V3_20260615_N6_USER_PROJECTION_AFTER_N5_REPLAY_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_ROLLBACK.sql`
- hard-fail before DELETE/UPDATE: true
- no CASCADE/DROP/TRUNCATE: true
- scope: this projection_run_id only
- preserves N5/N4/N3/N2/N1 facts and outbox status: true

## Forbidden Scope Proof

- N5 outbox consumed/updated: false
- N5 inbox/checkpoint write: false
- worker/scheduler started: false
- user_notification_queue write: false
- user_signal_decision refs: `0`
- sim order/trade/position refs: `0/0/0`
- virtual order/trade/position/pnl refs: `0/0/0/0`
- voice/mobile/position/order/real trade: false
- old system touched: false
