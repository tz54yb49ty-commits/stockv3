# V3 20260615 HINT 30m Stale Metric Pollution Audit

Result: `AUDIT_PASS`

## Target Case

`board:TDX:881470` at `2026-06-15 09:31` should not be `30m_volume`.

Corrected calculation:

```text
281104512 / 312718976 * 2613103496 = 2348930635.56391
2348930635.56391 < 2613103496
```

Therefore `BUY_HINT` amount pass is false. The correct N4 outcome is no `TriggerMatched` for this 09:31 HINT evidence.

## Stale Evidence

Three old N3 metric rows store `current_30m_virtual_amount=8433135360` for the same object/minute:

```text
91104  v3_n3_action_confirmation_metric_20260615_full_universe_replay_v1
121584 v3_n3_action_confirmation_metric_20260615_full_universe_formal_proof_enriched_v1
152064 v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_full_universe_v1
```

The corrected metric row is:

```text
182544 v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_policy_fix_v1
current_30m_virtual_amount=2348930635.56391
previous_day_same_window_amount=2613103496
```

## Linked N4/N5 Pollution

Target stale N4 matches:

```text
274210 v3_n4_trigger_replay_20260615_after_n3_full_universe_metric_v1
316873 v3_n4_trigger_replay_20260615_after_formal_proof_enrichment_v1
322805 v3_n4_trigger_replay_20260615_attachment_rule_canonical_v1
```

Linked N5 events:

```text
156089 ActionExecuted action_mark=30m_volume
160631 ActionExecuted action_mark=30m_volume
180087 ActionBlocked from stale N4 match
```

## Scope Summary

Known stale N4 BUY_HINT `30m_volume` refs:

```text
v3_n4_trigger_replay_20260615_after_n3_full_universe_metric_v1: 684
v3_n4_trigger_replay_20260615_after_formal_proof_enrichment_v1: 684
v3_n4_trigger_replay_20260615_attachment_rule_canonical_v1: 623
```

The policy-fix N4 run references corrected metric lineage:

```text
v3_n4_trigger_replay_20260615_attachment_rule_canonical_policy_fix_v1: 625
```

## Rollback Decision

Direct N5 rollback is not safe yet because N6 user projection refs exist for reviewed stale action runs. The next gate must choose scoped N6 rollback first or active-lineage supersession.

## Forbidden Scope

No DB writes, no rollback, no N4/N5/N6 execute, no outbox/inbox/checkpoint consume/update, no scheduler/worker, no voice/mobile/sim/position/order/trade, and no old-system access.

Next recommended gate: `V3_20260615_HINT_30M_STALE_FACT_SUPERSESSION_OR_ROLLBACK_POLICY_GATE`.
