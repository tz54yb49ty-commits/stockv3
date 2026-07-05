# N4/N5 Attachment Rule Canonical Alignment Post Review

Result: `POST_REVIEW_PASS`

This gate reviewed `docs/N4_N5_ATTACHMENT_RULE_CANONICAL_ALIGNMENT_IMPLEMENTATION_REPORT.json` and registers the implementation as the replay authority for the next 20260615 full-universe pass.

## Canonical Rules

- Ordinary formal BUY price: `current_price/current_close > previous_period_entity_high`.
- Ordinary formal SELL price: `current_price/current_close < previous_period_entity_low`.
- Ordinary formal price does not use current-period `body_high/body_low`.
- Ordinary formal amount uses the attachment D/W/M/Q/Y avg amount chain, not the old `current_period_amount > trigger_previous_amount_baseline` rule.
- `BUY:FULL` / `SELL:FULL` use D only.
- `BUY_HINT` / `SELL_HINT` use 30m calibrated amount only and do not require price breakthrough.
- 5m/30m virtual amount policy is `previous_day_same_window_elapsed_ratio_v1`.
- N5 consumes calibrated N3 metric and N4 proven trigger fields only; it does not recompute metrics or infer formal periods from `condition_key`.

## Validation

- targeted N3/N4/N5 tests: `96 OK`
- trigger test group: `150 OK`
- focused action/N4/N3 tests: `63 OK`
- `test_n5*.py`: `5 OK`
- `scripts/check_n4_contract.py`: `PASS`
- scoped compileall: `PASS`
- implementation report JSON parse: `PASS`
- scoped `git diff --check`: `PASS`

## Boundary

This post-review did not execute N3/N4/N5/N6, did not write the database, did not execute rollback, did not consume or update outbox/inbox/checkpoint, did not start scheduler/worker, and did not touch voice/mobile/sim/position/order/real trade or the old system.

## Decision

`attachment-rule-canonical` must be a new replay lineage. Existing `full-universe` and `formal-proof-enriched` closeouts remain historical evidence and must not be silently treated as the final attachment v2 closeout.

Next gate: `V3_20260615_ATTACHMENT_RULE_CANONICAL_FULL_UNIVERSE_REPLAY_CONTRACT_PREFLIGHT_GATE`.
