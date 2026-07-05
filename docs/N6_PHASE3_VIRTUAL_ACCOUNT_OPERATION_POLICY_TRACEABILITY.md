# N6 Phase 3 Virtual Account Operation Policy Traceability

Status: TRACEABILITY_PASS

Layer role: N6_user

Date: 2026-06-05

Traceability covers every rule in
`docs/N6_PHASE3_VIRTUAL_ACCOUNT_OPERATION_POLICY_DESIGN.md`.

## Summary

```text
rule_count=30
coverage=100%
duplicate_rule_ids=0
missing_rule_ids=0
```

## Rules

| Rule ID | Spec section | Component | Data source | Test target | Status |
|---|---|---|---|---|---|
| N6VA-OP-001 | Current Baseline | Admin virtual account | Phase 3 seed post-review proof | Future operation preflight verifies admin account and cash baseline | existing |
| N6VA-OP-002 | Current Baseline | Operation tables | 038C/038D/038E schema | Future runner preflight verifies order/trade/position/pnl baseline by scope | existing |
| N6VA-OP-003 | Policy Boundary | Virtual-only scope | AGENTS.md / architecture boundary | Future specs assert no real brokerage/account/funds/position semantics | doc |
| N6VA-OP-004 | Policy Boundary | Deterministic metadata | 038C-E schema fields | Future runners require run_id/policy_version/policy_hash/rollback_scope | planned |
| N6VA-OP-005 | Order Proposal | Proposal lifecycle | Operation design | Future proposal spec defines draft/reviewed/accepted/rejected/expired | planned |
| N6VA-OP-006 | Order Proposal | Proposal is not order | n6_virtual_order boundary | Future tests prove proposal gate does not write n6_virtual_order | planned |
| N6VA-OP-007 | Order Proposal | Accepted proposal requirement | Operation design | Future virtual order runner rejects non-accepted proposal | planned |
| N6VA-OP-008 | Order Proposal | N6 projection input | user_signal_projection/user_signal_card | Future proposal preflight rejects raw N4/N5 fact bypass | planned |
| N6VA-OP-009 | Order Proposal | ActionBlocked policy | N6 card state | Future proposal policy blocks ActionBlocked by default | planned |
| N6VA-OP-010 | Order Proposal | ActionExecuted policy | N6 card state | Future proposal policy allows candidate only, not real trade | planned |
| N6VA-OP-011 | Execution Policy | Trading calendar/time | Future execution policy artifact | Future tests cover calendar/session checks | planned |
| N6VA-OP-012 | Execution Policy | T+1 virtual availability | available/locked fields | Future execution policy tests T+1 without real position writes | planned |
| N6VA-OP-013 | Execution Policy | Halt/limit rules | Future market rule set | Future execution policy tests halt and limit blockers | planned |
| N6VA-OP-014 | Execution Policy | Deterministic fill seed | n6_virtual_trade.replay_deterministic_seed | Future trade runner tests deterministic replay | planned |
| N6VA-OP-015 | Fee/Tax Policy | Versioned policies | 038C fee/tax fields | Future fee/tax spec supplies policy versions and hashes | planned |
| N6VA-OP-016 | Fee/Tax Policy | No hard-coded rates | Operation design | Static tests prove no fee/tax rates in schema/runner defaults | planned |
| N6VA-OP-017 | Virtual Order Runner | Order write scope | n6_virtual_order | Future runner writes n6_virtual_order only | planned |
| N6VA-OP-018 | Virtual Trade Runner | Trade write scope | n6_virtual_trade/cash tables | Future runner writes trade plus cash ledger/snapshot deltas only | planned |
| N6VA-OP-019 | Position Materialization | Trade to event lineage | n6_virtual_trade/n6_virtual_position_event | Future materialization tests event appended before position state | planned |
| N6VA-OP-020 | Position Materialization | Current position state | n6_virtual_position | Future tests verify quantity = available + locked | planned |
| N6VA-OP-021 | Position Materialization | T+1 boundary | available/locked fields | Future tests prove no real position/common_position writes | planned |
| N6VA-OP-022 | PnL Valuation | Approved price policy | source_price_policy | Future valuation tests reject raw K/live price direct sources | planned |
| N6VA-OP-023 | PnL Valuation | Virtual-only PnL | n6_virtual_pnl_snapshot | Future UI/API labels PnL as not real return/advice | planned |
| N6VA-OP-024 | PnL Valuation | Formula checks | 038E CHECK constraints | Future valuation tests assert net and total asset formulas | existing |
| N6VA-OP-025 | Gate Roadmap | Gate order | Operation design | Runtime_control review verifies roadmap order | doc |
| N6VA-OP-026 | Rollback Model | Downstream-first rollback | Operation design | Future rollback SQL deletes PnL -> position -> trade -> order | planned |
| N6VA-OP-027 | Rollback Model | Upstream facts safety | N1-N6 boundary | Future rollback static tests prove no N5/N1-N5 fact mutation | planned |
| N6VA-OP-028 | Forbidden Scope | No delivery/push/voice/mobile | Operation design | Future runner reports side-effect flags false | planned |
| N6VA-OP-029 | Forbidden Scope | No sim/real trade/broker | Operation design | Future static tests reject broker/real_trade fields and API calls | planned |
| N6VA-OP-030 | Next Gate | Order proposal spec | Operation roadmap | Next review may enter N6_PHASE3_ORDER_PROPOSAL_SPEC_GATE | doc |

## Coverage

Every rule maps to a design section, component target, data source, and future
test or review target. Rows with status `planned` are not implementation claims.
