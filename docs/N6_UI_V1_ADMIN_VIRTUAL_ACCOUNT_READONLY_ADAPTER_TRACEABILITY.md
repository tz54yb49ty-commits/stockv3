# N6 UI v1 Admin Virtual Account Readonly Adapter Traceability

Status: DESIGN_PASS

Layer role: N6_user

Date: 2026-06-05

Coverage: 24 / 24 rules mapped.

Duplicate rule ids: 0

Missing rule ids: 0

| Rule ID | Spec section | Component | Data source | Test target | Status |
|---|---|---|---|---|---|
| N6UIVA-001 | Current Baseline | Adapter contract | Phase 3 seed post-review | Assert virtual_account_id=1 baseline is documented | doc |
| N6UIVA-002 | Scope | Repository | `n6_virtual_account` | Repository reads only virtual account table for account summary | planned |
| N6UIVA-003 | Scope | Repository | `n6_virtual_cash_snapshot` | Repository reads cash snapshot without mutation | planned |
| N6UIVA-004 | Scope | Repository | `n6_virtual_cash_ledger` | Repository reads recent immutable ledger rows | planned |
| N6UIVA-005 | Scope | Repository | none | Assert `user_sim_*` is not read for virtual account summary | planned |
| N6UIVA-006 | Implementation Plan | API | `n6_virtual_account` | `GET /api/n6/ui/v1/virtual-account` requires login | planned |
| N6UIVA-007 | API Contract | API | `n6_virtual_account` | virtual-account response hides write controls | planned |
| N6UIVA-008 | API Contract | API | `n6_virtual_cash_snapshot` | cash-snapshot response follows current pointer | planned |
| N6UIVA-009 | API Contract | API | `n6_virtual_cash_snapshot` | cash-snapshot preserves total_cash arithmetic | planned |
| N6UIVA-010 | API Contract | API | `n6_virtual_cash_ledger` | cash-ledger limit clamps to max 100 | planned |
| N6UIVA-011 | API Contract | API | N6 UI session | No virtual account POST/PUT/PATCH/DELETE routes exist | planned |
| N6UIVA-012 | UI Mock | Dashboard | account + snapshot | Dashboard renders account_name and cash fields | planned |
| N6UIVA-013 | UI Mock | Admin Account page | account + snapshot + ledger | Admin page renders three readonly sections | planned |
| N6UIVA-014 | UI Mock | Safety Banner | static model | Banner text includes READ ONLY / NO ORDER / NO TRADE / NO POSITION UPDATE | planned |
| N6UIVA-015 | Proposal Eligibility | Signal Detail | `user_signal_projection` | ActionBlocked displays only and does not generate proposal | planned |
| N6UIVA-016 | Proposal Eligibility | Signal Detail | `user_signal_projection` | ActionExecuted displays future eligibility without trade wording | planned |
| N6UIVA-017 | Proposal Eligibility | Signal Detail | `user_signal_projection` | ActionEligible displays future eligibility without proposal generation | planned |
| N6UIVA-018 | Proposal Eligibility | Signal Detail | `user_signal_projection` | ActionSkipped displays informational only | planned |
| N6UIVA-019 | Proposal Eligibility | Signal Detail | none | Forbidden wording is absent from UI/API | planned |
| N6UIVA-020 | Read-Only Boundary | API models | none | side_effects flags remain false | planned |
| N6UIVA-021 | Read-Only Boundary | Repository | N4/N5 outbox | Assert no outbox consumption/status update | planned |
| N6UIVA-022 | Read-Only Boundary | Repository | Phase 3 virtual tables | Assert no order/trade/position/pnl writes | planned |
| N6UIVA-023 | Test Plan | Static checks | source code | Static scan has no Phase 3 DML in adapter | planned |
| N6UIVA-024 | Next Gate | Runtime gate | artifacts | Implementation gate remains separate and readonly | doc |

## Gap Summary

All implementation items are planned gaps. They are expected because this gate
freezes the adapter design only and does not implement routes, repository
methods, templates, or tests.
