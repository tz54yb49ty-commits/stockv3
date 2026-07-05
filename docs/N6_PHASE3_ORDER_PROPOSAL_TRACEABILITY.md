# N6 Phase 3 Order Proposal Traceability

Status: TRACEABILITY_PASS

Layer role: N6_user

Date: 2026-06-05

Traceability covers every rule in `docs/N6_PHASE3_ORDER_PROPOSAL_SPEC.md`.

## Summary

```text
rule_count=28
coverage=100%
duplicate_rule_ids=0
missing_rule_ids=0
```

## Rules

| Rule ID | Spec section | Component | Data source | Test target | Status |
|---|---|---|---|---|---|
| N6OP-001 | Basis | Input artifact binding | Operation policy design and Phase 3 closeout | Review verifies all basis artifacts exist | doc |
| N6OP-002 | Proposal Concept | Proposal is not order | Operation policy design | Future proposal tests prove no n6_virtual_order write | planned |
| N6OP-003 | Proposal Concept | Cash boundary | n6_virtual_cash_ledger/snapshot | Future proposal tests prove no cash ledger/snapshot write | planned |
| N6OP-004 | Proposal Concept | Position boundary | n6_virtual_position tables | Future proposal tests prove no position/PnL write | planned |
| N6OP-005 | Proposal Concept | N5 outbox boundary | common_event_outbox | Future proposal tests prove no outbox status update | planned |
| N6OP-006 | Signal Eligibility | ActionBlocked rule | N6 card state | Future proposal policy blocks ActionBlocked by default | planned |
| N6OP-007 | Signal Eligibility | ActionExecuted rule | N5/N6 action state | Future proposal policy allows candidate but forbids order/fill language | planned |
| N6OP-008 | Signal Eligibility | ActionEligible rule | N5/N6 action state | Future proposal policy requires user policy permission | planned |
| N6OP-009 | Signal Eligibility | ActionSkipped rule | N5/N6 action state | Future proposal policy keeps skipped informational only | planned |
| N6OP-010 | Signal Eligibility | queued_only boundary | user_notification_queue | Future tests prove queued_only does not trigger proposal | planned |
| N6OP-011 | Data Boundary | Reviewed N5 source | N5 reviewed artifacts/events | Future preflight rejects unreviewed source events | planned |
| N6OP-012 | Data Boundary | N6 projection source | user_signal_projection/card | Future preflight uses N6 projection/card rather than raw N4/N5 fact bypass | planned |
| N6OP-013 | Data Boundary | Price source policy | N3/N6 reviewed snapshot or valuation policy | Future tests reject unapproved price source | planned |
| N6OP-014 | Data Boundary | Raw source ban | raw K / N1 raw facts / live data | Future static tests reject raw/live source access | planned |
| N6OP-015 | Lifecycle | Status enum | Proposal spec | Future schema CHECK includes candidate/reviewed/accepted/rejected/expired/superseded | planned |
| N6OP-016 | Lifecycle | Accepted-only order input | Proposal spec | Future virtual order runner rejects non-accepted proposal | planned |
| N6OP-017 | Field Draft | Required fields | Proposal field draft | Future schema draft includes required field set | planned |
| N6OP-018 | Field Draft | Lineage fields | source_lineage_json/run/policy fields | Future static tests prove deterministic lineage fields exist | planned |
| N6OP-019 | Review Rules | reviewed_by requirement | Proposal lifecycle | Future tests reject accepted/rejected without reviewer | planned |
| N6OP-020 | Review Rules | accepted_at requirement | Proposal lifecycle | Future tests reject accepted without accepted_at | planned |
| N6OP-021 | Review Rules | expired/superseded blocking | Proposal lifecycle | Future runner rejects expired/superseded proposal | planned |
| N6OP-022 | Forbidden Language | No order/fill wording | UI/API/report text | Future UI/API tests reject 已下单/已成交/真实交易/投资建议 | planned |
| N6OP-023 | Quality Gate | P0 blockers | Proposal preflight | Future dry-run/preflight reports P0 for boundary violations | planned |
| N6OP-024 | Rollback Boundary | Table-backed rollback | Future proposal table | Future rollback SQL deletes only proposal rows by scope | planned |
| N6OP-025 | Rollback Boundary | linked order guard | n6_virtual_order | Future rollback hard-fails if linked virtual order exists | planned |
| N6OP-026 | Rollback Boundary | Artifact-only rollback | Runtime registry/artifacts | Future artifact-only flow supersedes artifact without DB writes | planned |
| N6OP-027 | Future Gates | Gate sequence | Proposal spec | Runtime_control review validates schema/dry-run/review/order gate sequence | doc |
| N6OP-028 | Forbidden Scope | No execute side effects | AGENTS.md / operation policy | This gate leaves database_written/executed/outbox/worker flags false | doc |

## Coverage

Every rule maps to a spec section, component target, data source, and future
test or review target. Rows with status `planned` are not implementation
claims.
