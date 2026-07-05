# N6 Action Projection Traceability

Status: TRACEABILITY_PASS

Layer role: N6_user

Date: 2026-06-06

Coverage: 100%

Rules are continuous from `N6AP-001` to `N6AP-024`.

| Rule ID | Spec Section | Component Target | Data Source | Test Target | Status |
|---|---|---|---|---|---|
| N6AP-001 | Source Lineage | contract source | N5 readiness artifact | JSON source fields | doc |
| N6AP-002 | Input Scope | event reader | N5 canonical outbox | counts ActionExecuted=1 ActionBlocked=604 | planned |
| N6AP-003 | Input Scope | event reader | N5 canonical outbox | total input events=605 | planned |
| N6AP-004 | Input Scope | compatibility gate | legacy outbox | legacy ActionEvent/HintEvent/RiskEvent/PositionEvent rejected | planned |
| N6AP-005 | Input Scope | layer boundary | N4/N3/N2 | no raw fact substitution | doc |
| N6AP-006 | Projection Semantics | ActionExecuted card | N5 ActionExecuted | exact text 市场动作确认成立 | planned |
| N6AP-007 | Projection Semantics | ActionExecuted card | N5 ActionExecuted | no order/fill/real/virtual semantics | planned |
| N6AP-008 | Projection Semantics | ActionBlocked card | N5 ActionBlocked | exact text 市场动作未确认 | planned |
| N6AP-009 | Projection Semantics | blocked reason display | N5 reviewed payload/trace | no user-cash/position reinterpretation | planned |
| N6AP-010 | Planned Outputs | dry-run planner | contract counts | projection_run=1 | planned |
| N6AP-011 | Planned Outputs | dry-run planner | contract counts | projection/card=605/605 | planned |
| N6AP-012 | Planned Outputs | notification policy | contract policy | notification_queue=0 deferred | doc |
| N6AP-013 | Planned Outputs | mutation boundary | N6 tables | decision/proposal/order/trade/position/pnl=0 | doc |
| N6AP-014 | Principal Scope | principal resolver | admin principal/user | principal_scope=admin | planned |
| N6AP-015 | Principal Scope | access filter | N6 principal scope | no cross-principal read/write | planned |
| N6AP-016 | UI Boundary | A-track admin console | N6_UI_v1 freeze | hidden modules remain hidden | doc |
| N6AP-017 | UI Boundary | B-track isolation | N6 app shell | no B-track mutation | doc |
| N6AP-018 | Preflight | source action run check | N5 action run | exists and passed | planned |
| N6AP-019 | Preflight | baseline guard | N6 projection tables | source refs and scoped rows=0 | planned |
| N6AP-020 | Preflight | event id guard | N5 outbox/events | event_id total/distinct=605/605 | planned |
| N6AP-021 | Preflight | side-effect guard | N6/N5 refs | no delivery/sim/position/virtual refs | planned |
| N6AP-022 | Rollback | rollback plan | N6 projection run | delete card -> projection -> run | doc |
| N6AP-023 | Rollback | rollback hard-fail | downstream refs | block delivery/push/voice/mobile/sim/position/virtual/proposal refs | doc |
| N6AP-024 | Next Gate | gate control | runtime_control handoff | dry-run allowed, execute still separate | doc |

## Coverage Summary

```text
rule_count=24
covered_rules=24
coverage=100%
duplicate_rules=0
missing_rules=0
```

## Current Gaps

```text
dry_run_runner_not_executed=true
db_fresh_preflight_not_refreshed_in_this_gate=true
notification_queue_materialization_deferred=true
execute_final_gate_not_opened=true
```
