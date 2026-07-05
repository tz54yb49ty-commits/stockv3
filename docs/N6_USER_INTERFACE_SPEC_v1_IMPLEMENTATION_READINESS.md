# N6 User Interface Spec v1 Implementation Readiness

Result: `IMPLEMENTATION_READINESS_PASS`

## Summary

- Rule count: 42
- Implemented: 41
- Partial: 1
- Gaps: 0
- Traceability coverage: 100.0%

## Implemented APIs

- `GET /api/n6/ui/v1/signals`
- `GET /api/n6/ui/v1/signals/{user_signal_projection_id}`
- `GET /api/n6/ui/v1/dashboard/metrics`
- `GET /api/n6/ui/v1/artifacts`
- `GET /api/n6/ui/v1/rollback-summary`

## Component Plan

- Dashboard
- Signal List
- Signal Detail
- ActionBlocked Card
- ActionExecuted Card
- Notification Preview
- Audit Panel
- Shared Status Label

## Readiness Matrix

| rule_id | component | API | data_source | status | gap | test |
|---|---|---|---|---|---|---|
| N6UI-001 | All N6 pages | `get dashboard metrics`<br>`list signals`<br>`get signal detail`<br>`get artifact links`<br>`get rollback summary` | `user_signal_projection`, `user_signal_card`, `user_notification_queue` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-002 | All N6 pages | `get dashboard metrics`<br>`list signals`<br>`get signal detail`<br>`get artifact links`<br>`get rollback summary` | N6 projection rows, reviewed artifacts | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-003 | N6 repository layer | `list signals`<br>`get signal detail`<br>`get dashboard metrics`<br>`get artifact links`<br>`get rollback summary` | N6 projection/card/queue, N4/N5/N6 artifacts | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-004 | Dashboard metric tile | `get dashboard metrics` | `user_signal_card` or N6 report artifact | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_dashboard_artifacts_and_rollback_summary_are_read_only` |
| N6UI-005 | Dashboard metric tile | `get dashboard metrics` | `user_signal_card.action_state`, `user_signal_projection.action_state` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_dashboard_artifacts_and_rollback_summary_are_read_only` |
| N6UI-006 | Dashboard metric tile | `get dashboard metrics` | `user_signal_card.action_state`, `user_signal_projection.action_state` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_dashboard_artifacts_and_rollback_summary_are_read_only` |
| N6UI-007 | Dashboard metric tile | `get dashboard metrics` | `user_notification_queue.queue_status` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_dashboard_artifacts_and_rollback_summary_are_read_only` |
| N6UI-008 | Dashboard metric tile | `get dashboard metrics` | `user_notification_queue.queue_status`, `user_notification_queue.notification_source` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_dashboard_artifacts_and_rollback_summary_are_read_only` |
| N6UI-009 | Dashboard metric tile | `get dashboard metrics` | N6 run/report artifact, rollback artifact path | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_dashboard_artifacts_and_rollback_summary_are_read_only` |
| N6UI-010 | Dashboard run header | `get dashboard metrics`<br>`get artifact links` | `user_projection_run.user_projection_run_id` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_dashboard_artifacts_and_rollback_summary_are_read_only` |
| N6UI-011 | Signal List table | `list signals` | `user_signal_card`, `user_signal_projection` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-012 | Signal List table | `list signals` | `user_signal_card`, `user_signal_projection` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-013 | Signal List table | `list signals` | `user_signal_card.card_payload_json`, `user_signal_projection.trace_json` when projected | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-014 | Signal List table | `list signals` | N6 projected payload/context fields | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-015 | Signal List table | `list signals` | `user_notification_queue.queue_status`, `source_action_run_id` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-016 | Signal List filters | `list signals` | N6 card/projection fields | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_filters_apply_without_side_effects` |
| N6UI-017 | Signal List actions | `list signals`<br>`get signal detail`<br>`get artifact links` | Current filtered N6 rows | partial | detail navigation is implemented through GET /api/n6/ui/v1/signals/{user_signal_projection_id}; export current filtered list is still a future UI route/action. | `Open detail, lineage navigation, export filtered list tests` |
| N6UI-018 | Signal Detail lineage sections | `get signal detail`<br>`get artifact links` | N4/N5/N6 report artifacts, N6 rows | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_detail_shows_lineage_audit_and_sanitized_preview` |
| N6UI-019 | Signal Detail audit summary | `get signal detail`<br>`get artifact links`<br>`get rollback summary` | `run_id`, `event_id`, artifacts, rollback SQL | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_detail_shows_lineage_audit_and_sanitized_preview` |
| N6UI-020 | ActionBlocked Card | `get signal detail`<br>`list signals` | `user_signal_card.action_state=blocked` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-021 | ActionBlocked Card | `get signal detail`<br>`list signals` | Rendered card text | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-022 | ActionBlocked Card | `get signal detail`<br>`list signals` | N5 projected blocked_reason | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-023 | ActionBlocked Card | `get signal detail`<br>`list signals` | Rendered card reason text | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-024 | ActionBlocked Card | `get signal detail`<br>`list signals` | Rendered card text | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-025 | ActionExecuted Card | `get signal detail`<br>`list signals` | `user_signal_card.action_state=executed` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-026 | ActionExecuted Card | `get signal detail`<br>`list signals` | Rendered card text | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-027 | ActionExecuted Card | `get signal detail`<br>`list signals` | Rendered card text | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-028 | Notification Preview | `get signal detail`<br>`list signals` | `user_notification_queue.queue_status` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_detail_shows_lineage_audit_and_sanitized_preview` |
| N6UI-029 | Notification Preview | `get signal detail`<br>`list signals` | `user_notification_queue.notification_payload_json` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_detail_shows_lineage_audit_and_sanitized_preview` |
| N6UI-030 | Notification Preview | `get signal detail`<br>`list signals` | sanitized `notification_payload_json` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_detail_shows_lineage_audit_and_sanitized_preview` |
| N6UI-031 | Audit Panel | `get signal detail`<br>`get artifact links`<br>`get rollback summary` | N6 rows, N4/N5/N6 artifacts, rollback SQL paths | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_detail_shows_lineage_audit_and_sanitized_preview` |
| N6UI-032 | Audit Panel | `get signal detail`<br>`get artifact links`<br>`get rollback summary` | UI route/action set | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_detail_shows_lineage_audit_and_sanitized_preview` |
| N6UI-033 | Disabled placeholders | `get dashboard metrics` | UI state only | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_detail_shows_lineage_audit_and_sanitized_preview` |
| N6UI-034 | All N6 pages | `get dashboard metrics`<br>`list signals`<br>`get signal detail`<br>`get artifact links`<br>`get rollback summary` | Gate artifacts | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-035 | Shared status label component | `list signals`<br>`get signal detail`<br>`get dashboard metrics` | N6 card/queue/run status fields | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-036 | Shared status label component | `list signals`<br>`get signal detail`<br>`get dashboard metrics` | Rendered status labels | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-037 | ActionEligible display | `list signals`<br>`get signal detail` | `action_state=eligible` | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-038 | ActionSkipped display | `list signals`<br>`get signal detail` | `action_state=skipped` or expired context | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-039 | Artifact status label | `get artifact links` | Artifact timestamp/run comparison | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_dashboard_artifacts_and_rollback_summary_are_read_only` |
| N6UI-040 | Artifact status label | `get artifact links` | Run supersede metadata/artifact status | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_dashboard_artifacts_and_rollback_summary_are_read_only` |
| N6UI-041 | UI wording tests | `list signals`<br>`get signal detail` | Rendered ActionBlocked/ActionExecuted cards | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |
| N6UI-042 | UI boundary tests | `list signals`<br>`get signal detail`<br>`get dashboard metrics`<br>`get artifact links`<br>`get rollback summary` | Route map/repository calls/action handlers | implemented | none | `tests/test_n6_user_app.py::test_ui_v1_signal_list_components_are_read_only_and_wording_safe` |

## Forbidden Scope Proof

- database_written: `false`
- n5_outbox_consumed_or_updated: `false`
- n6_outbox_inbox_checkpoint_written: `false`
- worker_started: `false`
- delivery_push_voice_mobile_triggered: `false`
- sim_position_real_trade_triggered: `false`

## Current Gaps

- N6UI-017: Filtered list export/download action remains a later UI enhancement; the detail API for lineage navigation is implemented.
