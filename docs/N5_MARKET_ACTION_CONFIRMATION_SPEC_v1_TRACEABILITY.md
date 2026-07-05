# N5 Market Action Confirmation Spec v1 Traceability

Status: frozen_for_runtime_control_review

Frozen at: 2026-06-04

Source spec:

```text
docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1.md
```

Traceability rule IDs are intentionally continuous from `N5-001` to `N5-064`. Each rule maps to a spec section, implementation target, test target, and current status.

Status legend:

```text
existing = already represented by current canonical docs or recent N5 alignment work
planned  = required future implementation or test work
gap      = known divergence or missing enforcement
doc      = documentation / runtime_control policy rule
```

| Rule ID | Rule | Spec Section | Implementation Target | Test Target | Status |
|---|---|---|---|---|---|
| N5-001 | N5 is the market action confirmation layer and only confirms market action facts. | 1 | `src/ashare_v3/action/execute.py`, `src/ashare_v3/action/dry_run.py` | `tests/test_action_execute.py`, `tests/test_action_dry_run.py` | existing |
| N5-002 | N5 must not confirm user trade eligibility, holdings, cash, T+1, blacklist, display, voice, sim, or real trade. | 1, 2 | action runner boundary guards | no user/voice/mobile/sim/position/real trade tests | existing |
| N5-003 | N5 may consume N4 standard trigger events. | 2 | N5 consumer planner / runner | consumer input tests | existing |
| N5-004 | N5 may read N3 standard action-confirmation metric facts. | 2, 5 | N3 metric join in dry-run/execute | metric join tests | existing |
| N5-005 | N5 may preserve immutable N4 trace/context without reinterpreting upstream responsibilities. | 2 | trace serialization | trace payload tests | planned |
| N5-006 | N5 must not pull realtime quotes or call external market data adapters. | 2, 5 | import/static guard, runner guard | static forbidden adapter tests | existing |
| N5-007 | N5 must not read raw minute K to assemble confirmation indicators. | 2, 5 | metric-only data access path | no raw minute read tests | planned |
| N5-008 | N5 must not query N1 daily K or recompute N2 conditions. | 2 | layer access guard | static forbidden upstream read tests | existing |
| N5-009 | N5 must not recompute N4 trigger decisions or write N4 trigger facts/outbox status. | 2, 18 | execute transaction scope | N4 preservation tests | existing |
| N5-010 | N5 must not read user holdings/account/cash/blacklist/T+1/preferences. | 2, 13 | forbidden table/import guards | no user state read tests | planned |
| N5-011 | `TriggerMatched` is the only action confirmation entry. | 3.1 | event dispatch planner | TriggerMatched action fact tests | existing |
| N5-012 | `TriggerPendingMarketData` is observer/quality/watermark only. | 3.2 | event dispatch planner | pending no action fact tests | existing |
| N5-013 | `TriggerStateChanged` is state/tracking gate only and cannot create fresh action fact. | 3.3 | event dispatch planner | state changed no action fact tests | existing |
| N5-014 | N5 may write inbox/checkpoint for all three N4 event types only when execute is authorized. | 16 | execute consumer persistence | scoped inbox/checkpoint tests | existing |
| N5-015 | Consumer/watermark progress must not be confused with action entry. | 16 | planner grain builder | pending/state no action event tests | existing |
| N5-016 | N5 action entry requires current_status=matched. | 3.1, 4 | input validator | non-matched blocked tests | planned |
| N5-017 | N5 action entry requires trigger_live=true. | 3.1, 4 | input validator | trigger_not_live tests | planned |
| N5-018 | N5 action entry requires action_eligible=true. | 3.1, 4 | input validator | ineligible input tests | planned |
| N5-019 | Runtime signal_type is only B_BUY or S_SELL. | 4 | signal guard | deprecated signal rejection tests | existing |
| N5-020 | B_BUY_30M_VOL, S_SELL_30M_SHRINK, BUY_HINT, SELL_HINT are not runtime signal_type in new N5. | 4, 9 | signal normalization guard | deprecated runtime signal tests | existing |
| N5-021 | Deprecated signal names may appear only in condition_key/original_condition_key/trace/historical compatibility. | 4, 9 | trace field handling | trace-only hint tests | existing |
| N5-022 | N5 must resolve source_action_confirmation_metric_id to N3 metric facts. | 4, 5 | metric repository / join service | metric ref present/resolved tests | existing |
| N5-023 | N5 must not trust opaque payload.action_confirmation as final proof. | 5 | planner input source selection | opaque payload ignored tests | existing |
| N5-024 | Required metric families are 120m, 30m, 5m, and 1m action-confirmation metrics. | 5 | metric model/repository | all metric family required tests | planned |
| N5-025 | N5 metric join is scoped by asset_kind, identity_key, trade_date, metric id, minute/time, and lineage. | 5 | metric repository | lineage mismatch tests | planned |
| N5-026 | N5 may use N3 numeric fields or deterministic pass flags only when traceable to metric facts. | 5 | metric evaluator | pass flag traceability tests | planned |
| N5-027 | B_BUY requires 120m current_price > previous_120m_body_high. | 6 | buy evaluator | buy 120m price tests | existing |
| N5-028 | B_BUY requires 30m current_price > previous_30m_body_high. | 6 | buy evaluator | buy 30m price tests | existing |
| N5-029 | B_BUY requires 5m current_price > previous_5m_body_high. | 6 | buy evaluator | buy 5m price tests | existing |
| N5-030 | B_BUY requires current_5m_virtual_amount > previous_5m_full_amount. | 6 | buy evaluator | buy 5m amount tests | existing |
| N5-031 | B_BUY requires 1m current_price > previous_1m_body_high. | 6 | buy evaluator | buy 1m price tests | existing |
| N5-032 | B_BUY requires current_1m_amount > previous_1m_amount outside first 1m boundary. | 6, 8 | buy evaluator | buy 1m amount tests | existing |
| N5-033 | S_SELL requires 120m current_price < previous_120m_body_low. | 7 | sell evaluator | sell 120m price tests | existing |
| N5-034 | S_SELL requires 30m current_price < previous_30m_body_low. | 7 | sell evaluator | sell 30m price tests | existing |
| N5-035 | S_SELL requires 5m current_price < previous_5m_body_low. | 7 | sell evaluator | sell 5m price tests | existing |
| N5-036 | S_SELL requires current_5m_virtual_amount < previous_5m_full_amount. | 7 | sell evaluator | sell 5m amount tests | existing |
| N5-037 | S_SELL requires 1m current_price < previous_1m_body_low. | 7 | sell evaluator | sell 1m price tests | existing |
| N5-038 | S_SELL requires current_1m_amount < previous_1m_amount outside first 1m boundary. | 7, 8 | sell evaluator | sell 1m amount tests | existing |
| N5-039 | First 1m amount comparison defaults pass, but price still uses previous trading day's last 1m body. | 8 | boundary evaluator | first 1m boundary tests | existing |
| N5-040 | First 5m amount comparison defaults pass, but price still uses previous trading day's last 5m body. | 8 | boundary evaluator | first 5m boundary tests | existing |
| N5-041 | First 30m price uses previous trading day's last 30m body. | 8 | boundary evaluator | first 30m boundary tests | planned |
| N5-042 | First 120m price uses previous trading day's last 120m body. | 8 | boundary evaluator | first 120m boundary tests | planned |
| N5-043 | Missing previous session reference must block with missing_previous_session_reference and must not default pass. | 8, 13 | boundary evaluator | missing previous reference tests | existing |
| N5-044 | BUY_HINT maps to B_BUY, trigger_kind=hint, original_condition_key=BUY_HINT, trigger_mark_candidate=30m_volume. | 9 | N4/N5 payload normalizer | BUY_HINT mapping tests | existing |
| N5-045 | SELL_HINT maps to S_SELL, trigger_kind=hint, original_condition_key=SELL_HINT, trigger_mark_candidate=30m_shrink. | 9 | N4/N5 payload normalizer | SELL_HINT mapping tests | existing |
| N5-046 | HINT provenance uses the same B_BUY/S_SELL four-period rules as ordinary signals. | 9 | evaluator | hint same-rule tests | existing |
| N5-047 | N5 must not emit HintEvent for BUY_HINT/SELL_HINT in canonical runtime. | 9, 11 | event factory | no HintEvent tests | existing |
| N5-048 | N5 does not rejudge 30m volume/shrink and only consumes N4 trigger_mark_candidate. | 10 | evaluator / action mark mapper | no 30m recompute tests | planned |
| N5-049 | final action_mark may be only normal, 30m_volume, or 30m_shrink. | 10 | action fact/event validation | action_mark enum tests | existing |
| N5-050 | final action_mark is written only when confirmation_status=passed. | 10 | action fact/event builder | blocked action_mark null tests | existing |
| N5-051 | blocked, failed, pending, skipped, expired, or quality-only plans must keep final action_mark null. | 10 | action fact/event builder | non-passed action_mark null tests | existing |
| N5-052 | Canonical output events are ActionEligible, ActionBlocked, ActionExecuted, and ActionSkipped. | 11 | event factory | canonical event type tests | existing |
| N5-053 | ActionEvent, HintEvent, RiskEvent, and PositionEvent are historical compatibility only. | 11 | event factory guard | no legacy output tests | existing |
| N5-054 | ActionExecuted means market action confirmation passed and does not mean trade/sim/display/voice/notification. | 12 | event payload / docs / UI wording | ActionExecuted boundary tests | doc |
| N5-055 | ActionBlocked means market/system action confirmation not confirmed and not user trade failure. | 13 | event payload / report wording | ActionBlocked wording tests | existing |
| N5-056 | Allowed blocked_reason values are metric/system/confirmation facts only. | 13 | blocked_reason enum/validator | allowed reason tests | existing |
| N5-057 | User-layer reasons such as no_position, insufficient_cash, T+1, already_sold, position_limit, blacklist are forbidden in N5. | 13 | blocked_reason validator | forbidden reason tests | existing |
| N5-058 | Canonical action_state values are eligible, blocked, executed, skipped, expired. | 14 | schema/event validation | action_state enum tests | existing |
| N5-059 | Expired is represented by ActionSkipped with action_state=expired; no ActionExpired event is added. | 14 | event factory | no ActionExpired tests | existing |
| N5-060 | N5 dedupe grain uses trade_date, identity_key, signal_type, trigger_kind, original_condition_key, primary_trigger_period, trigger_mark_candidate, trigger_time. | 15 | dedupe key builder | dedupe key tests | existing |
| N5-061 | Same-minute multiple condition_key rows are merged into one action confirmation grain and provenance is preserved in trace_json. | 15 | dedupe / trace builder | same-minute merge tests | existing |
| N5-062 | If the same grain already has ActionExecuted, N5 must not write another ActionExecuted. | 15 | idempotency guard | duplicate executed tests | planned |
| N5-063 | Execute source_run_id must be explicitly allowlisted and synthetic/stale/unexpected source runs must be denied. | 17 | runner source guard | allowlist/denylist tests | existing |
| N5-064 | N5 business rollback is scoped, hard-fail guarded, and must not touch N4/N3/N2/N6. | 18 | rollback SQL generator | rollback guard tests | existing |

## Coverage Summary

```text
rule_id_start=N5-001
rule_id_end=N5-064
rule_count=64
duplicate_rule_ids=0
missing_rule_ids=0
core_rule_coverage=100%
```

## Current Gap Summary

```text
gap:
  none for the implementation-alignment items covered by this gate.

planned:
  Strict lineage mismatch tests for mismatched projection/source lineage remain future hardening.
  Duplicate already-executed action grain idempotency tests remain future hardening.
  Static guards that prove N5 never reads user holdings/account tables remain future hardening.
  Runtime-control dashboard detector for N5 v1 status mismatch remains future work.

doc:
  Runtime control must confirm this spec freeze before implementation alignment.
```
