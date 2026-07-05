# N6 User Interface Spec v1 Dry-Run / Preview Plan

Result: `DRY_RUN_PREVIEW_PASS`

Layer role: `N6_user`
Generated at: `2026-06-04T22:14:33+08:00`

This artifact is an implementation dry-run and preview plan only. It does not change code, write database rows, execute runners, consume outbox rows, start workers, or perform delivery, push, voice, mobile, sim, position, or real trade side effects.

## Input Summary

```text
rule_count=42
traceability_coverage=42/42
status_counts={'doc': 3, 'gap': 24, 'planned': 15}
```

## 1. N6 UI Implementation Plan

Implementation should be split into a read-only repository layer, read-only API handlers, UI components, and traceability-driven tests. The repository layer must query only N6 projection/card/queue tables and reviewed artifact metadata. It must not query raw K-line facts, user funds/position, sim, real trade, delivery provider tables, or N3/N4/N5 internal facts as a substitute for N6 projection.

## 2. Component Plan

| Component | Status | Rules | API | Data sources | Display / purpose |
|---|---|---|---|---|---|
| Dashboard | `planned` | N6UI-004, N6UI-005, N6UI-006, N6UI-007, N6UI-008, N6UI-009, N6UI-010 | get dashboard metrics, get artifact links, get rollback summary | user_signal_card, user_signal_projection, user_notification_queue, reviewed N6 report artifacts | One-screen read-only runtime status for selected trade date/run context. Display: today_signal_count, ActionBlocked count, ActionExecuted count, queued_only count, pending delivery count, rollback_safe status, latest run_id. |
| Signal List | `gap` | N6UI-011, N6UI-012, N6UI-013, N6UI-014, N6UI-015, N6UI-016, N6UI-017 | list signals | user_signal_card, user_signal_projection, user_notification_queue | Main read-only scan table with filters, lineage navigation, and export. Display: trade_date, identity_key, asset_kind, signal_type, action_state, action_mark, blocked_reason, trigger_kind, original_condition_key, primary_trigger_period, trigger_time, queue_status, source_action_run_id. |
| Signal Detail | `gap` | N6UI-018, N6UI-019 | get signal detail, get artifact links, get rollback summary | user_signal_projection, user_signal_card, user_notification_queue, source N4/N5/N6 artifacts | Read-only lineage and audit context for one projected signal. Display: N4 lineage, N5 lineage, N6 lineage, run_id, event_id, rollback_safe, artifact links, rollback SQL link. |
| ActionBlocked Card | `gap` | N6UI-020, N6UI-021, N6UI-022, N6UI-023, N6UI-024 | list signals, get signal detail | user_signal_card.action_state=blocked, card_payload_json/display_payload_json reviewed fields | Explain that market action confirmation failed without implying user/trade/account failure. Display: title=市场动作未确认, approved blocked_reason only, no trade-failure wording. |
| ActionExecuted Card | `gap` | N6UI-025, N6UI-026, N6UI-027 | list signals, get signal detail | user_signal_card.action_state=executed, card_payload_json/display_payload_json reviewed fields | Show N5 market-action confirmation fact without implying order/trade/position side effects. Display: primary_text=市场动作确认成立, no 已成交/已下单/已交易 wording. |
| Notification Preview | `planned` | N6UI-028, N6UI-029, N6UI-030 | list signals, get signal detail | user_notification_queue.queue_status, user_notification_queue.notification_payload_json | Render queue state and sanitized preview payload without provider delivery or outbox updates. Display: queued_only, preview, delivered, sanitized payload only. |
| Audit Panel | `gap` | N6UI-031, N6UI-032 | get signal detail, get artifact links, get rollback summary | N6 rows, N4/N5/N6 reviewed artifacts, rollback SQL paths | Expose lineage/artifact/rollback evidence without mutation controls. Display: run_id, rollback SQL, rollback_safe, artifact links, source_action_run_id, source event_id. |
| Shared Status Label | `planned/gap` | N6UI-035, N6UI-036, N6UI-037, N6UI-038, N6UI-039, N6UI-040 | list signals, get signal detail, get dashboard metrics, get artifact links | N6 card/queue/run status fields, artifact status metadata | Reusable textual status labels with color as secondary cue only. Display: blocked, executed, eligible, skipped, queued_only, preview, delivered, rollback_safe, stale_artifact, superseded. |

## 3. Read-Only API Plan

| API | Method | Path | Query | Read sources | Forbidden sources | Side effects |
|---|---|---|---|---|---|---|
| list signals | `GET` | `/api/n6/ui/v1/signals` | trade_date, asset_kind, signal_type, action_state, blocked_reason, queue_status, limit, cursor | user_signal_card, user_signal_projection, user_notification_queue | raw K-line tables, N3/N4/N5 internal facts as substitute, user account cash/funds/position, sim tables, real trade tables | none; no outbox update, no delivery, no worker |
| get signal detail | `GET` | `/api/n6/ui/v1/signals/{user_signal_projection_id}` | include=lineage,audit,queue | user_signal_projection, user_signal_card, user_notification_queue, reviewed N4/N5/N6 artifacts | raw market facts for recompute, position/sim/real trade tables | none; read-only detail assembly |
| get dashboard metrics | `GET` | `/api/n6/ui/v1/dashboard/metrics` | trade_date, projection_run_id | user_signal_card, user_signal_projection, user_notification_queue, reviewed N6 report artifacts | N5 outbox status mutation, delivery provider state unless reviewed artifact | none; read-only aggregate counts |
| get artifact links | `GET` | `/api/n6/ui/v1/artifacts` | projection_run_id, source_action_run_id, source_trigger_run_id | reviewed artifact registry or checked docs paths | unreviewed raw run output as authoritative display | none; returns links and stale/superseded labels |
| get rollback summary | `GET` | `/api/n6/ui/v1/rollback-summary` | projection_run_id, source_action_run_id | reviewed rollback artifact paths, N6 post-review reports | rollback execution endpoints, mutation command registry | none; display only, no rollback command execution |

## 4. Field Mapping

### user_signal_projection

```json
{
  "identity": [
    "user_signal_projection_id",
    "user_projection_run_id",
    "user_id"
  ],
  "list_fields": [
    "asset_kind",
    "identity_key",
    "code",
    "name",
    "direction",
    "signal_type",
    "action_state",
    "action_mark",
    "condition_key",
    "original_condition_key"
  ],
  "lineage_fields": [
    "source_layer",
    "source_event_id",
    "source_outbox_id",
    "source_event_type",
    "source_action_event_id",
    "source_action_run_id",
    "source_condition_display_run_id"
  ],
  "payload_fields": [
    "display_payload_json",
    "trace_json",
    "projection_policy"
  ],
  "ui_policy": "read-only projection source; do not recompute N4/N5 or pull market data"
}
```

### user_signal_card

```json
{
  "identity": [
    "user_signal_card_id",
    "user_signal_projection_id",
    "user_projection_run_id",
    "user_id"
  ],
  "list_fields": [
    "card_type",
    "card_status",
    "title",
    "summary",
    "asset_kind",
    "identity_key",
    "code",
    "name",
    "direction",
    "signal_type",
    "action_state",
    "action_mark"
  ],
  "display_fields": [
    "target_price",
    "current_price",
    "expected_return_pct",
    "board_code",
    "board_name"
  ],
  "payload_fields": [
    "card_payload_json",
    "trace_json",
    "projection_policy"
  ],
  "ui_policy": "primary source for cards; wording must obey ActionBlocked/ActionExecuted rules"
}
```

### user_notification_queue

```json
{
  "identity": [
    "user_notification_queue_id",
    "user_projection_run_id",
    "user_signal_projection_id",
    "user_signal_card_id",
    "user_id"
  ],
  "list_fields": [
    "notification_source",
    "queue_status",
    "channel",
    "title",
    "message",
    "priority",
    "asset_kind",
    "identity_key"
  ],
  "lineage_fields": [
    "source_event_id",
    "source_action_run_id",
    "source_action_event_id",
    "source_action_event_type"
  ],
  "payload_fields": [
    "notification_payload_json",
    "trace_json",
    "projection_policy"
  ],
  "ui_policy": "display queue/preview state only; queued_only/preview must not trigger provider delivery or outbox update"
}
```

### source_artifacts

```json
{
  "N4": [
    "docs/N4_TRIGGER_RULE_SPEC_v4_EXECUTE_REPORT.md",
    "docs/N4_TRIGGER_RULE_SPEC_v4_execute_report.json"
  ],
  "N5": [
    "docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_20260603_POST_REVIEW.md",
    "docs/N5_MARKET_ACTION_CONFIRMATION_SPEC_v1_20260603_post_review.json"
  ],
  "N6": [
    "docs/N6_20260603_V1_MARKET_ACTION_CONFIRMATION_PROJECTION_POST_REVIEW.md",
    "docs/N6_20260603_v1_market_action_confirmation_projection_post_review.json"
  ],
  "rollback": [
    "sql/N6_projection_business_rollback.sql",
    "sql/N5_market_action_confirmation_spec_v1_20260603_execute_rollback.sql"
  ],
  "ui_policy": "artifact links are display evidence only; UI must not execute rollback SQL"
}
```

## 5. Test Plan

| Test | Assertion | Rules |
|---|---|---|
| ActionBlocked wording | ActionBlocked card title is exactly 市场动作未确认 and never 交易失败. | N6UI-020, N6UI-021 |
| ActionExecuted wording | ActionExecuted card never displays 已成交/已下单/已交易 and does not imply order/fill/position/cash mutation. | N6UI-025, N6UI-026, N6UI-027 |
| queued_only boundary | queued_only renders as queued-only dashboard state and does not call notification delivery APIs. | N6UI-007, N6UI-028, N6UI-029 |
| preview no outbox update | Notification Preview renders sanitized payload and never consumes/updates N5 outbox. | N6UI-029, N6UI-030, N6UI-042 |
| no raw K reads | Repository/API tests fail if UI queries raw K-line tables or N3 market facts to recompute display. | N6UI-002, N6UI-003, N6UI-042 |
| no user funds/position reads | Repository/API tests fail if UI reads user account cash/funds/position by default. | N6UI-003, N6UI-024, N6UI-027 |
| disabled future entrypoints | Delivery/push/voice/mobile/sim/position/real trade controls are disabled placeholders and no mutation endpoint exists. | N6UI-033, N6UI-034, N6UI-042 |
| status label coverage | Shared label component renders required text labels; color never replaces text. | N6UI-035, N6UI-036, N6UI-037, N6UI-038, N6UI-039, N6UI-040 |
| audit panel read-only | Audit Panel shows rollback SQL path and artifact links but has no rollback execution control. | N6UI-031, N6UI-032 |

## 6. Implementation Readiness Matrix

| rule_id | component | API | data_source | status | gap | test |
|---|---|---|---|---|---|---|
| `N6UI-001` | All N6 pages | get dashboard metrics, list signals, get signal detail, get artifact links, get rollback summary | `user_signal_projection`, `user_signal_card`, `user_notification_queue` | `planned` | planned UI/read-only API implementation evidence missing | UI smoke shows cards/queues/status without raw tables |
| `N6UI-002` | All N6 pages | get dashboard metrics, list signals, get signal detail, get artifact links, get rollback summary | N6 projection rows, reviewed artifacts | `doc` | none; enforce as boundary in implementation tests | Static/read-only boundary test: no N3/N4/N5 recompute or market pull calls |
| `N6UI-003` | N6 repository layer | list signals, get signal detail, get dashboard metrics, get artifact links, get rollback summary | N6 projection/card/queue, N4/N5/N6 artifacts | `gap` | implementation/test evidence missing | Repository tests only query allowed sources |
| `N6UI-004` | Dashboard metric tile | get dashboard metrics | `user_signal_card` or N6 report artifact | `planned` | planned UI/read-only API implementation evidence missing | Dashboard today signal count test |
| `N6UI-005` | Dashboard metric tile | get dashboard metrics | `user_signal_card.action_state`, `user_signal_projection.action_state` | `planned` | planned UI/read-only API implementation evidence missing | Dashboard ActionBlocked count test |
| `N6UI-006` | Dashboard metric tile | get dashboard metrics | `user_signal_card.action_state`, `user_signal_projection.action_state` | `planned` | planned UI/read-only API implementation evidence missing | Dashboard ActionExecuted count test |
| `N6UI-007` | Dashboard metric tile | get dashboard metrics | `user_notification_queue.queue_status` | `planned` | planned UI/read-only API implementation evidence missing | Dashboard queued_only count test |
| `N6UI-008` | Dashboard metric tile | get dashboard metrics | `user_notification_queue.queue_status`, `user_notification_queue.notification_source` | `planned` | planned UI/read-only API implementation evidence missing | Dashboard pending delivery count test |
| `N6UI-009` | Dashboard metric tile | get dashboard metrics | N6 run/report artifact, rollback artifact path | `planned` | planned UI/read-only API implementation evidence missing | Dashboard rollback_safe display test |
| `N6UI-010` | Dashboard run header | get dashboard metrics, get artifact links | `user_projection_run.user_projection_run_id` | `planned` | planned UI/read-only API implementation evidence missing | Dashboard latest run_id test |
| `N6UI-011` | Signal List table | list signals | `user_signal_card`, `user_signal_projection` | `gap` | implementation/test evidence missing | Table renders trade_date, identity_key, asset_kind |
| `N6UI-012` | Signal List table | list signals | `user_signal_card`, `user_signal_projection` | `gap` | implementation/test evidence missing | Table renders signal_type, action_state, action_mark |
| `N6UI-013` | Signal List table | list signals | `user_signal_card.card_payload_json`, `user_signal_projection.trace_json` when projected | `gap` | implementation/test evidence missing | Table renders blocked_reason |
| `N6UI-014` | Signal List table | list signals | N6 projected payload/context fields | `gap` | implementation/test evidence missing | Table renders trigger_kind, original_condition_key, primary_trigger_period, trigger_time |
| `N6UI-015` | Signal List table | list signals | `user_notification_queue.queue_status`, `source_action_run_id` | `gap` | implementation/test evidence missing | Table renders queue_status and source_action_run_id |
| `N6UI-016` | Signal List filters | list signals | N6 card/projection fields | `gap` | implementation/test evidence missing | Filters apply trade_date, asset_kind, signal_type, action_state, blocked_reason |
| `N6UI-017` | Signal List actions | list signals, get signal detail, get artifact links | Current filtered N6 rows | `gap` | implementation/test evidence missing | Open detail, lineage navigation, export filtered list tests |
| `N6UI-018` | Signal Detail lineage sections | get signal detail, get artifact links | N4/N5/N6 report artifacts, N6 rows | `gap` | implementation/test evidence missing | Detail renders N4/N5/N6 lineage |
| `N6UI-019` | Signal Detail audit summary | get signal detail, get artifact links, get rollback summary | `run_id`, `event_id`, artifacts, rollback SQL | `gap` | implementation/test evidence missing | Detail renders run_id, event_id, rollback_safe, source artifacts, rollback SQL |
| `N6UI-020` | ActionBlocked Card | get signal detail, list signals | `user_signal_card.action_state=blocked` | `gap` | implementation/test evidence missing | Exact title assertion: 市场动作未确认 |
| `N6UI-021` | ActionBlocked Card | get signal detail, list signals | Rendered card text | `gap` | implementation/test evidence missing | Negative wording assertion: no 交易失败 |
| `N6UI-022` | ActionBlocked Card | get signal detail, list signals | N5 projected blocked_reason | `gap` | implementation/test evidence missing | Approved blocked_reason allowlist test |
| `N6UI-023` | ActionBlocked Card | get signal detail, list signals | Rendered card reason text | `gap` | implementation/test evidence missing | Forbidden user-layer reason denylist test |
| `N6UI-024` | ActionBlocked Card | get signal detail, list signals | Rendered card text | `gap` | implementation/test evidence missing | No trade/sim/position/account failure implication test |
| `N6UI-025` | ActionExecuted Card | get signal detail, list signals | `user_signal_card.action_state=executed` | `gap` | implementation/test evidence missing | Exact text assertion: 市场动作确认成立 |
| `N6UI-026` | ActionExecuted Card | get signal detail, list signals | Rendered card text | `gap` | implementation/test evidence missing | Negative wording assertion: no 已成交/已下单/已交易 |
| `N6UI-027` | ActionExecuted Card | get signal detail, list signals | Rendered card text | `gap` | implementation/test evidence missing | No sim/order/fill/position/cash implication test |
| `N6UI-028` | Notification Preview | get signal detail, list signals | `user_notification_queue.queue_status` | `planned` | planned UI/read-only API implementation evidence missing | queued_only/preview/delivered state rendering test |
| `N6UI-029` | Notification Preview | get signal detail, list signals | `user_notification_queue.notification_payload_json` | `planned` | planned UI/read-only API implementation evidence missing | Preview does not imply provider delivery/push/voice/mobile/ack |
| `N6UI-030` | Notification Preview | get signal detail, list signals | sanitized `notification_payload_json` | `planned` | planned UI/read-only API implementation evidence missing | Forbidden payload keys absent from UI preview |
| `N6UI-031` | Audit Panel | get signal detail, get artifact links, get rollback summary | N6 rows, N4/N5/N6 artifacts, rollback SQL paths | `gap` | implementation/test evidence missing | Audit fields render test |
| `N6UI-032` | Audit Panel | get signal detail, get artifact links, get rollback summary | UI route/action set | `doc` | none; enforce as boundary in implementation tests | No rollback execution control test |
| `N6UI-033` | Disabled placeholders | get dashboard metrics | UI state only | `gap` | implementation/test evidence missing | Disabled delivery/push/voice/mobile/sim/position/real trade controls test |
| `N6UI-034` | All N6 pages | get dashboard metrics, list signals, get signal detail, get artifact links, get rollback summary | Gate artifacts | `doc` | none; enforce as boundary in implementation tests | Static route/action test: no real side-effect endpoints without gate |
| `N6UI-035` | Shared status label component | list signals, get signal detail, get dashboard metrics | N6 card/queue/run status fields | `planned` | planned UI/read-only API implementation evidence missing | Label set includes all required status labels |
| `N6UI-036` | Shared status label component | list signals, get signal detail, get dashboard metrics | Rendered status labels | `planned` | planned UI/read-only API implementation evidence missing | Text remains visible independent of color |
| `N6UI-037` | ActionEligible display | list signals, get signal detail | `action_state=eligible` | `gap` | implementation/test evidence missing | Eligible rendered as watch candidate, not buy instruction |
| `N6UI-038` | ActionSkipped display | list signals, get signal detail | `action_state=skipped` or expired context | `gap` | implementation/test evidence missing | Skipped rendered informational, not system error |
| `N6UI-039` | Artifact status label | get artifact links | Artifact timestamp/run comparison | `planned` | planned UI/read-only API implementation evidence missing | stale_artifact label test |
| `N6UI-040` | Artifact status label | get artifact links | Run supersede metadata/artifact status | `planned` | planned UI/read-only API implementation evidence missing | superseded label test |
| `N6UI-041` | UI wording tests | list signals, get signal detail | Rendered ActionBlocked/ActionExecuted cards | `gap` | implementation/test evidence missing | Test suite contains exact and forbidden wording assertions |
| `N6UI-042` | UI boundary tests | list signals, get signal detail, get dashboard metrics, get artifact links, get rollback summary | Route map/repository calls/action handlers | `gap` | implementation/test evidence missing | Test suite asserts read-only and forbidden side-effect boundaries |

## Remaining Gaps

```text
gap_count=24
planned_count=15
doc_count=3
gap_rules=N6UI-003,N6UI-011,N6UI-012,N6UI-013,N6UI-014,N6UI-015,N6UI-016,N6UI-017,N6UI-018,N6UI-019,N6UI-020,N6UI-021,N6UI-022,N6UI-023,N6UI-024,N6UI-025,N6UI-026,N6UI-027,N6UI-031,N6UI-033,N6UI-037,N6UI-038,N6UI-041,N6UI-042
planned_rules=N6UI-001,N6UI-004,N6UI-005,N6UI-006,N6UI-007,N6UI-008,N6UI-009,N6UI-010,N6UI-028,N6UI-029,N6UI-030,N6UI-035,N6UI-036,N6UI-039,N6UI-040
```

## Next Gate

Allowed next gate: `N6_USER_INTERFACE_SPEC_v1_IMPLEMENTATION_GATE`.

The next gate may implement read-only UI repository/API/components/tests. It must not write database rows, consume/update outbox, start workers, or enable delivery, push, voice, mobile, sim, position, or real trade side effects.

## Forbidden Scope

```text
code_changed=false
database_written=false
execute_ran=false
outbox_consumed=false
worker_started=false
delivery=false
push=false
voice=false
mobile=false
sim=false
position=false
real_trade=false
```
