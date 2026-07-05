# N6 User Interface Spec v1 Traceability

Status: SPEC_FREEZE_PASS

Layer role: N6_user

Date: 2026-06-04

This traceability matrix maps every frozen N6 UI rule to its section,
component target, data source, test target, and current status.

Coverage:

```text
rules_total=42
mapped_rules=42
coverage=100%
```

Status legend:

```text
existing: backing N6 data or artifact already exists
planned: UI implementation is planned from this rule
gap: current UI is known not to satisfy the rule yet
doc: normative boundary documented here
```

| Rule | Spec section | Component | Data source | Test target | Status |
|---|---|---|---|---|---|
| N6UI-001 | 1 Purpose | All N6 pages | `user_signal_projection`, `user_signal_card`, `user_notification_queue` | UI smoke shows cards/queues/status without raw tables | planned |
| N6UI-002 | 1 Purpose | All N6 pages | N6 projection rows, reviewed artifacts | Static/read-only boundary test: no N3/N4/N5 recompute or market pull calls | doc |
| N6UI-003 | 2 Data Sources | N6 repository layer | N6 projection/card/queue, N4/N5/N6 artifacts | Repository tests only query allowed sources | gap |
| N6UI-004 | 3.1 Dashboard | Dashboard metric tile | `user_signal_card` or N6 report artifact | Dashboard today signal count test | planned |
| N6UI-005 | 3.1 Dashboard | Dashboard metric tile | `user_signal_card.action_state`, `user_signal_projection.action_state` | Dashboard ActionBlocked count test | planned |
| N6UI-006 | 3.1 Dashboard | Dashboard metric tile | `user_signal_card.action_state`, `user_signal_projection.action_state` | Dashboard ActionExecuted count test | planned |
| N6UI-007 | 3.1 Dashboard | Dashboard metric tile | `user_notification_queue.queue_status` | Dashboard queued_only count test | planned |
| N6UI-008 | 3.1 Dashboard | Dashboard metric tile | `user_notification_queue.queue_status`, `user_notification_queue.notification_source` | Dashboard pending delivery count test | planned |
| N6UI-009 | 3.1 Dashboard | Dashboard metric tile | N6 run/report artifact, rollback artifact path | Dashboard rollback_safe display test | planned |
| N6UI-010 | 3.1 Dashboard | Dashboard run header | `user_projection_run.user_projection_run_id` | Dashboard latest run_id test | planned |
| N6UI-011 | 3.2 Signal List | Signal List table | `user_signal_card`, `user_signal_projection` | Table renders trade_date, identity_key, asset_kind | gap |
| N6UI-012 | 3.2 Signal List | Signal List table | `user_signal_card`, `user_signal_projection` | Table renders signal_type, action_state, action_mark | gap |
| N6UI-013 | 3.2 Signal List | Signal List table | `user_signal_card.card_payload_json`, `user_signal_projection.trace_json` when projected | Table renders blocked_reason | gap |
| N6UI-014 | 3.2 Signal List | Signal List table | N6 projected payload/context fields | Table renders trigger_kind, original_condition_key, primary_trigger_period, trigger_time | gap |
| N6UI-015 | 3.2 Signal List | Signal List table | `user_notification_queue.queue_status`, `source_action_run_id` | Table renders queue_status and source_action_run_id | gap |
| N6UI-016 | 3.2 Signal List | Signal List filters | N6 card/projection fields | Filters apply trade_date, asset_kind, signal_type, action_state, blocked_reason | gap |
| N6UI-017 | 3.2 Signal List | Signal List actions | Current filtered N6 rows | Open detail, lineage navigation, export filtered list tests | gap |
| N6UI-018 | 3.3 Signal Detail | Signal Detail lineage sections | N4/N5/N6 report artifacts, N6 rows | Detail renders N4/N5/N6 lineage | gap |
| N6UI-019 | 3.3 Signal Detail | Signal Detail audit summary | `run_id`, `event_id`, artifacts, rollback SQL | Detail renders run_id, event_id, rollback_safe, source artifacts, rollback SQL | gap |
| N6UI-020 | 3.4 ActionBlocked Card | ActionBlocked Card | `user_signal_card.action_state=blocked` | Exact title assertion: 市场动作未确认 | gap |
| N6UI-021 | 3.4 ActionBlocked Card | ActionBlocked Card | Rendered card text | Negative wording assertion: no 交易失败 | gap |
| N6UI-022 | 3.4 ActionBlocked Card | ActionBlocked Card | N5 projected blocked_reason | Approved blocked_reason allowlist test | gap |
| N6UI-023 | 3.4 ActionBlocked Card | ActionBlocked Card | Rendered card reason text | Forbidden user-layer reason denylist test | gap |
| N6UI-024 | 3.4 ActionBlocked Card | ActionBlocked Card | Rendered card text | No trade/sim/position/account failure implication test | gap |
| N6UI-025 | 3.5 ActionExecuted Card | ActionExecuted Card | `user_signal_card.action_state=executed` | Exact text assertion: 市场动作确认成立 | gap |
| N6UI-026 | 3.5 ActionExecuted Card | ActionExecuted Card | Rendered card text | Negative wording assertion: no 已成交/已下单/已交易 | gap |
| N6UI-027 | 3.5 ActionExecuted Card | ActionExecuted Card | Rendered card text | No sim/order/fill/position/cash implication test | gap |
| N6UI-028 | 3.6 Notification Preview | Notification Preview | `user_notification_queue.queue_status` | queued_only/preview/delivered state rendering test | planned |
| N6UI-029 | 3.6 Notification Preview | Notification Preview | `user_notification_queue.notification_payload_json` | Preview does not imply provider delivery/push/voice/mobile/ack | planned |
| N6UI-030 | 3.6 Notification Preview | Notification Preview | sanitized `notification_payload_json` | Forbidden payload keys absent from UI preview | planned |
| N6UI-031 | 3.7 Audit Panel | Audit Panel | N6 rows, N4/N5/N6 artifacts, rollback SQL paths | Audit fields render test | gap |
| N6UI-032 | 3.7 Audit Panel | Audit Panel | UI route/action set | No rollback execution control test | doc |
| N6UI-033 | 3.8 Disabled Future Entrypoints | Disabled placeholders | UI state only | Disabled delivery/push/voice/mobile/sim/position/real trade controls test | gap |
| N6UI-034 | 5 Safety Boundary | All N6 pages | Gate artifacts | Static route/action test: no real side-effect endpoints without gate | doc |
| N6UI-035 | 4 Status Labels and Colors | Shared status label component | N6 card/queue/run status fields | Label set includes all required status labels | planned |
| N6UI-036 | 4 Status Labels and Colors | Shared status label component | Rendered status labels | Text remains visible independent of color | planned |
| N6UI-037 | 4 Status Labels and Colors | ActionEligible display | `action_state=eligible` | Eligible rendered as watch candidate, not buy instruction | gap |
| N6UI-038 | 4 Status Labels and Colors | ActionSkipped display | `action_state=skipped` or expired context | Skipped rendered informational, not system error | gap |
| N6UI-039 | 4 Status Labels and Colors | Artifact status label | Artifact timestamp/run comparison | stale_artifact label test | planned |
| N6UI-040 | 4 Status Labels and Colors | Artifact status label | Run supersede metadata/artifact status | superseded label test | planned |
| N6UI-041 | 6 Implementation Rules | UI wording tests | Rendered ActionBlocked/ActionExecuted cards | Test suite contains exact and forbidden wording assertions | gap |
| N6UI-042 | 6 Implementation Rules | UI boundary tests | Route map/repository calls/action handlers | Test suite asserts read-only and forbidden side-effect boundaries | gap |

## Current Gaps

Implementation gaps:

```text
Dashboard metrics are not normalized to this spec.
Signal List required columns and filters are incomplete.
Signal Detail lineage and artifact links are incomplete.
ActionBlocked and ActionExecuted exact wording tests do not exist yet.
Notification Preview rendering must be aligned with sanitized payload policy.
Audit Panel rollback SQL and artifact link rendering is incomplete.
Disabled sim/position/real trade placeholders are not standardized.
Shared status label component is not yet frozen in UI code.
Traceability-driven UI tests are not yet implemented.
```

Data/model gaps to verify during implementation:

```text
blocked_reason projection field must be consistently available or derived from reviewed N6 payload fields.
trigger_kind and primary_trigger_period must be mapped from existing N6 payload/context fields without reading N4/N5 raw tables.
stale_artifact and superseded labels need reviewed artifact/run metadata.
```

## Review Gate

Allowed next step:

```text
runtime_control N6 UI spec review gate
```

Implementation remains blocked until a separate N6 UI implementation gate.
