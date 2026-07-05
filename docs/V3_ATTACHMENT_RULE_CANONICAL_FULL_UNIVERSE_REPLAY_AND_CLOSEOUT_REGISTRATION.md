# V3 Attachment Rule Canonical Full-Universe Replay Closeout Registration

- result: `CLOSEOUT_PASS`
- completion_marker: `V3_ATTACHMENT_RULE_CANONICAL_FULL_UNIVERSE_REPLAY_AND_CLOSEOUT_COMPLETE`
- trade_date: `20260615`

## Active Lineage

- N3 metric: `v3_n3_action_confirmation_metric_20260615_attachment_rule_canonical_policy_fix_v1`
- N4 trigger: `v3_n4_trigger_replay_20260615_attachment_rule_canonical_policy_fix_v1`
- N5 action: `v3_n5_action_replay_20260615_attachment_rule_canonical_policy_fix_v1`
- N6 user projection: `v3_n6_user_projection_20260615_attachment_rule_canonical_policy_fix_v1`

## Superseded Evidence

The earlier `attachment_rule_canonical_v1` lineage is retained as historical evidence only. Its N5 replay blocked all `5853` matched events with `metric_policy_invalid` because N3 full-day metric rows did not yet carry the calibrated virtual amount policy envelope.

## Proof

- full universe source: `V3_N2_minute_target_scope_and_N4_trigger_context_snapshot`
- old system read: `false`
- universe objects stock/index/board/total: `1894/83/127/2104`
- N3 metric rows stock/index/board/total: `454560/19440/30480/504480`
- N3 calibrated policy coverage: `100%` in `raw_json.virtual_amount_policy_version` and `trace_json.virtual_amount_policy.policy_version`
- N4 outbox: `TriggerMatched=6074`, `TriggerPendingMarketData=24745`, `TriggerStateChanged=20067`
- N4 ordinary formal 30m contamination: `0`
- N5 outbox: `ActionExecuted=2998`, `ActionBlocked=3076`
- N5 `metric_policy_invalid`: `0`
- N5 `metric_missing`: `0`
- N6 user projection/card/queue: `2998/2998/0`

## Boundary

- target machine / old system read: `false`
- scheduler / worker started: `false`
- N5 outbox consumed or status updated: `false`
- voice/mobile/sim/position/order/real trade touched: `false`
