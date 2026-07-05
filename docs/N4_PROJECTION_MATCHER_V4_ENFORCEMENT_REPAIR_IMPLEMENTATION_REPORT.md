# N4 Projection Matcher v4 Enforcement Repair Implementation Report

## Result

IMPLEMENTATION_PASS

## Supersession Notice

This report's broad wording that `TriggerMatched` globally forbids `trigger_period=30m` is superseded by `docs/N4_HINT_30M_TRIGGER_PERIOD_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.md`.

Corrected rule:

- ordinary `trigger_kind=trigger` still forbids `trigger_period=30m`
- HINT `trigger_kind=hint` with `condition_key=BUY_HINT / SELL_HINT` allows `trigger_period=30m`
- `30m` remains forbidden in `triggered_periods / all_trigger_periods / primary_trigger_period`

Generated at: 2026-06-08T14:49:10+08:00

Layer role: N4_trigger

## Scope

This gate repaired the N4 projection matcher v4 enforcement breach only. It did not execute the N4 matcher, did not write business database rows, did not consume or update N3 outbox/inbox/checkpoint rows, did not enter N5/N6, and did not start workers.

## Breach Being Repaired

The rolled-back run `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952` had promoted 30m projection evidence into invalid `TriggerMatched` rows:

- `TriggerMatched=320`
- `trigger_price missing=320`
- `trigger_kind missing=320`
- `n5_entry_allowed missing=320`
- `trigger_period=30m=320`
- `state.primary_trigger_period=30m / all_trigger_periods=["30m"]`

## Implementation Summary

1. 30m projection evidence is no longer allowed in formal trigger period fields.
   - Forbidden for `TriggerMatched`: `trigger_period`, `triggered_periods`, `all_trigger_periods`, `primary_trigger_period`.
   - Allowed only as projection evidence: `projection_period`, `projection_30m_type`, `projection_30m_flag`, `trigger_mark_candidate`, and projection trace/raw JSON.

2. `TriggerMatched` now fails closed before write planning or execution when v4 required fields are missing or invalid.
   - Requires `trigger_price`.
   - Requires `trigger_kind`.
   - Requires `n5_entry_allowed=true`.
   - Requires canonical runtime `signal_type in {B_BUY, S_SELL}`.
   - Blocks `30m` in formal period fields.
   - Blocks invalid N5 entry contract.

3. Ordinary BUY/SELL 30m projection evidence is no longer promoted to `TriggerMatched`.
   - It becomes `TriggerPendingMarketData`.
   - `trigger_live=false`.
   - `current_status=pending_market_data`.
   - `n5_entry_allowed=false`.
   - It writes no `common_trigger_match` row in execute planning.

4. `BUY_HINT` / `SELL_HINT` remain allowed projection-confirmed trigger entries.
   - They carry `trigger_kind=hint`.
   - They must carry `trigger_price` from approved N3 projection facts.
   - They keep formal trigger periods empty instead of writing `30m`.
   - Their 30m evidence remains in projection fields.

5. N4 projection matcher event payload no longer emits `action_mark`.
   - It emits `trigger_mark_candidate`.
   - Final `action_mark` remains an N5 responsibility.

## Modified Files

- `src/ashare_v3/trigger/v4_enforcement.py`
- `src/ashare_v3/trigger/projection_matcher.py`
- `src/ashare_v3/trigger/projection_matcher_execute.py`
- `src/ashare_v3/events/models.py`
- `tests/test_n4_v4_enforcement.py`
- `tests/test_trigger_projection_matcher.py`
- `tests/test_trigger_projection_matcher_execute.py`
- `docs/N4_PROJECTION_MATCHER_V4_ENFORCEMENT_REPAIR_IMPLEMENTATION_REPORT.md`
- `docs/N4_PROJECTION_MATCHER_V4_ENFORCEMENT_REPAIR_IMPLEMENTATION_REPORT.json`

## v4 Enforcement Proof

- `trigger_period="30m"` is blocked by `invalid_trigger_period_30m`.
- `primary_trigger_period="30m"` is blocked by `invalid_primary_trigger_period_30m`.
- `triggered_periods` or `all_trigger_periods` containing `30m` are blocked.
- Missing `trigger_price`, missing `trigger_kind`, or `n5_entry_allowed=false/missing` blocks invalid `TriggerMatched` before writes.
- `TriggerPendingMarketData` is not inserted into `common_trigger_match`.
- Pending rows keep `trigger_live=false` and `current_status=pending_market_data`.
- Valid `TriggerMatched` payload includes `trigger_price`, `trigger_kind`, and `n5_entry_allowed=true`.

## Static Scan Proof

Static scan found no production write path that assigns `trigger_period='30m'` for `TriggerMatched`.

The remaining production matches are enforcement blockers in `v4_enforcement.py`; test matches are regression fixtures that prove the breach shape is blocked.

## Validation Summary

Passed:

- `PYTHONPATH=src python3 -m unittest tests.test_n4_v4_enforcement tests.test_trigger_projection_matcher tests.test_trigger_projection_matcher_execute`
- `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_trigger_projection_matcher*.py'`
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_n4*.py'`
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_trigger*.py'`
- `python3 -m compileall scripts src tests`
- `PYTHONPATH=src python3 scripts/check_n4_contract.py`
- JSON parse for source contract, rollback post-review, and old execute report
- JSON parse for this implementation report
- `git diff --check`

## Boundary Proof

- `business_database_written=false`
- `n4_matcher_executed=false`
- `rollback_executed=false`
- `n3_outbox_consumed_or_updated=false`
- `common_event_inbox_checkpoint_touched=false`
- `n5_n6_entered=false`
- `worker_started=false`
- `delivery_push_voice_mobile=false`
- `sim_position_pnl_real_trade=false`
- `proposal_order_trade=false`
- `old_system_touched=false`

## Remaining Notes

This gate repaired N4 projection matcher enforcement only. If runtime_control wants an additional N5 consumer-side guard that rejects any historical or future invalid TriggerMatched payload, that should be a separate `layer_role=N5_action` gate.

## Next Gate

Allowed next route:

`runtime_control -> N4_PROJECTION_MATCHER_V4_ENFORCEMENT_REPAIR_POST_REVIEW_GATE`

Do not execute N4 matcher until runtime_control post-review and a refreshed dry-run/preflight/final gate explicitly pass.
