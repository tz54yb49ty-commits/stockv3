# V3 20260615 N6 User Projection Execute Preflight

- gate: `V3_20260615_N6_USER_PROJECTION_AFTER_N5_REPLAY_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_CONTRACT_PREFLIGHT_GATE`
- result: `PREFLIGHT_PASS`
- layer_role: `N6_user`
- source_action_run_id: `v3_n5_action_replay_20260615_after_n4_repaired_formal_price_amount_chain_and_n3_coverage_repair_v1`
- projection_run_id: `v3_n6_user_projection_20260615_after_n5_replay_repaired_formal_price_amount_chain_and_n3_coverage_repair_v1`

## Source N5 Proof

- common_action_run.status: `passed`
- P0/P1/P2: `0/0/0`
- pending outbox total: `1029`
- ActionExecuted pending: `68`
- ActionEligible pending: `0`
- ActionBlocked pending: `961`
- delivered/delivering: `0/0` by absence from status distribution

## User Message Filter

Only `ActionEligible` and `ActionExecuted` may become ordinary user messages. `ActionBlocked` and `ActionSkipped` remain status-monitor / diagnosis inputs.

## Planned Writes If A Later Execute Gate Is Approved

- user_projection_run: `1`
- user_signal_projection: `68`
- user_signal_card: `68`
- user_notification_queue: `0` (deferred)

This gate does not authorize execute and wrote no business rows.

## Rollback

- rollback SQL: `sql/V3_20260615_N6_USER_PROJECTION_AFTER_N5_REPLAY_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_ROLLBACK.sql`
- scope: only `v3_n6_user_projection_20260615_after_n5_replay_repaired_formal_price_amount_chain_and_n3_coverage_repair_v1`
- hard-fail before first DELETE/UPDATE: true
- preserves N5/N4/N3/N2/N1 facts and outbox/inbox/checkpoint: true

## Forbidden Scope

No N6 execute, no N5 outbox consume/update, no N6 inbox/checkpoint write, no scheduler/worker, no delivery/push/voice/mobile, no sim/position/order/real trade, no old system read/modify.
