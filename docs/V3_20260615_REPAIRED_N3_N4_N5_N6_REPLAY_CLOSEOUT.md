# V3 20260615 Repaired N3-N6 Replay Closeout

Result: `CLOSEOUT_PASS`

## Active Lineage

- N3 metric run: `action_confirmation_projection_metric_20260615_repaired_formal_price_amount_chain_coverage_repair_v1__n4_20260615_repaired_formal_price_amount_chain_replay_v1`
- N4 trigger run: `n4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_v1`
- N5 action run: `v3_n5_action_replay_20260615_after_n4_repaired_formal_price_amount_chain_and_n3_coverage_repair_v1`
- N6 projection run: `v3_n6_user_projection_20260615_after_n5_replay_repaired_formal_price_amount_chain_and_n3_coverage_repair_v1`

Active UI policy: use repaired N6 projection lineage only. Stale old lineage remains historical evidence only.

## Final Chain Summary

| Layer | Result | Key Counts |
| --- | --- | --- |
| N3 metric coverage repair | passed | stock/index/board/total `1894/81/127/2102`, metric_ready `2102`, quality-visible excluded `36` |
| N4 repaired replay | passed | `TriggerMatched=1029`, `TriggerPendingMarketData=3696`, `TriggerStateChanged=0` |
| N5 replay | passed | `ActionExecuted=68`, `ActionBlocked=961`, `ActionEligible=0`, `ActionSkipped=0` |
| N6 projection | passed | `user_projection_run=1`, `user_signal_projection=68`, `user_signal_card=68`, `user_notification_queue=0` |

N5 outbox remains pending and was not consumed: pending `1029`, delivered/delivering `0/0`.

## Rollback Registry

- N3: `sql/N3_20260615_action_confirmation_metric_coverage_repair_rollback.sql`
- N4: `sql/N4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_rollback.sql`
- N5: `sql/V3_20260615_n5_replay_after_n4_repaired_formal_price_amount_chain_and_n3_coverage_repair_rollback.sql`
- N6: `sql/V3_20260615_N6_USER_PROJECTION_AFTER_N5_REPLAY_REPAIRED_FORMAL_PRICE_AMOUNT_CHAIN_ROLLBACK.sql`

All rollback SQL is scoped, hard-fails before executable `DELETE` / `UPDATE`, and does not use `DROP`, `TRUNCATE`, or `CASCADE`.

## Remaining Caveats

- N3 P1 remains: N4 payload metric id was not backfilled; downstream lineage uses deterministic join/link proof.
- N4 execute wrote expected rows and live proof passed, but the command process returned exit code `2` after write. Do not rerun the same execute command; repair runner post-execute status propagation/idempotency separately.
- N5 checkpoint rows should be interpreted from the scoped execute/post-review report; the live checkpoint table behaves like aggregate/watermark state.
- N6 notification queue remains deferred. Display enrichment warnings are non-blocking.
- Stale old lineage must remain historical-only and must not be used by active UI.

## Forbidden Scope Proof

This closeout did not start scheduler/worker, did not consume N5 outbox, did not update outbox/inbox/checkpoint, did not enter voice/mobile/sim/position/order/real trade, and did not touch the old system.

## Next Gate

Recommended next gate:

```text
V3_20260615_REPAIRED_LINEAGE_ACTIVE_UI_VERIFICATION_GATE
```

Purpose: read-only verify that the active UI and message APIs use the repaired N6 projection lineage and exclude stale historical lineage from active views.
