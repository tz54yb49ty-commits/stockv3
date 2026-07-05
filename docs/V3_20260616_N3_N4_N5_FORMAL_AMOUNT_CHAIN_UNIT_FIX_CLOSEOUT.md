# V3 20260616 N3-N4-N5 Formal Amount Chain Unit Fix Closeout

Result: `CLOSEOUT_PASS`

Layer role: `runtime_control`

Scope: read-only closeout registration. N6 remains deferred.

## Final Chain Summary

N3 implementation passed:

- Daily amount seeds are interpreted as `thousand_yuan` and converted to `yuan`.
- Canonical unit policy is `formal_amount_chain_thousand_yuan_to_yuan_v1`.
- `*_avg_with_today` uses `(current_amount_total_seed_yuan + today_virt_amount_yuan) / (current_trade_days_seed + 1)`.
- Missing or invalid seed/unit proof fails closed.

N4 guard passed:

- Ordinary formal BUY/SELL/FULL requires `unit_conversion_policy=formal_amount_chain_thousand_yuan_to_yuan_v1`.
- Ordinary formal requires `amount_unit=yuan` and `amount_rule=attachment_dwmqy_avg_chain`.
- HINT 30m calibrated path is unchanged.

Stale N5 rollback passed:

- Stale action run `v3_n5_action_replay_20260616_after_n4_trigger_price_repair_v1` was cleaned.
- Post-check rows: `common_action_run=0`, action facts `0/0/0`, `common_action_event=0`, N5 outbox `0`.
- Dedicated N4 inbox/checkpoint for the stale consumer is `0/0`.

Repaired N4 replay passed:

- Run: `v3_n4_trigger_replay_20260616_until_1401_v1`
- `TriggerMatched=159`
- `TriggerPendingMarketData=4539`
- `TriggerStateChanged=0`
- Ordinary formal `B_BUY/S_SELL TriggerMatched=0/0`
- HINT matched: `BUY_HINT=3`, `SELL_HINT=156`
- Pending rows are not N5 entries.

Repaired N5 replay passed:

- Run: `v3_n5_action_replay_20260616_after_n4_formal_amount_chain_unit_proof_guard_v1`
- `ActionExecuted=7`
- `ActionBlocked=152`
- `ActionEligible=0`
- `ActionSkipped=0`
- Metric join `159/159`, `metric_missing=0`
- N5 outbox remains pending `159`, delivered/delivering `0/0`.

## Active Lineage Registry

- N3 metric: `action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- N4 trigger: `v3_n4_trigger_replay_20260616_until_1401_v1`
- N5 action: `v3_n5_action_replay_20260616_after_n4_formal_amount_chain_unit_proof_guard_v1`
- N5 consumer: `n5_action_consumer_v1_20260616_formal_amount_chain_unit_proof_guard_replay`
- N6: deferred

## 002831 False-Positive Resolution Proof

Case:

- Asset: `stock:SZ:002831`
- Trade date: `20260616`
- Time: `14:01`
- Condition: `BUY:Q,M,W,D`
- Old false-positive: ordinary formal `W` led to stale `ActionExecuted`.

Read-only live proof:

- Old stale N5 run live rows:
  - `common_action_run=0`
  - `common_action_event=0`
  - N5 outbox `0`
- New N4 rows for `stock:SZ:002831 / BUY:Q,M,W,D`: `0`
- New N4 `W TriggerMatched` for this condition: `0`
- New N5 action events for this condition: `0`
- New N5 `W ActionExecuted` for this condition: `0`

Conclusion: the old stale `ActionExecuted` was removed, and the repaired lineage does not produce an ordinary formal `W` action for this case.

## Rollback Registry

- Stale N5 rollback SQL: `sql/V3_20260616_n5_action_after_n4_trigger_price_repair_rollback.sql`
- Repaired N4 rollback SQL: `sql/V3_20260616_n4_trigger_replay_rollback.sql`
- Repaired N5 rollback SQL: `sql/V3_20260616_n5_action_after_n4_formal_amount_chain_unit_proof_guard_rollback.sql`

Rollback SQL is scoped and guarded. Closeout did not execute rollback.

## Deferred N6 Proof

- N6 entered: `false`
- User projection refs: `0`
- User signal projection/card refs: `0/0`
- User notification queue refs: `0`
- Position refs: `0/0`
- N5 outbox consumed: `false`

## Forbidden Scope Proof

- No N3/N4/N5/N6 execution by this closeout gate.
- No database writes by this closeout gate.
- No rollback execution.
- No outbox/inbox/checkpoint consumption or update.
- No scheduler/worker start.
- No voice/mobile/sim/position/order/real trade.
- Old system untouched.

## Next Recommended Gate

`V3_20260616_FORMAL_AMOUNT_CHAIN_UNIT_FIX_N6_DEFERRED_POLICY_GATE`
