# N6 User Interface Spec v1 Post-Review

Result: `POST_REVIEW_ARTIFACT_PASS`

Layer role: `runtime_control`
Generated at: `2026-06-04T22:09:01+08:00`

This artifact materializes the frozen N6 UI spec and traceability into a post-review summary. It does not change code, write database rows, execute runners, consume outbox rows, start workers, or perform delivery, push, voice, mobile, sim, position, or real trade side effects.

## A. Rule Summary

| rule_id | title | component | data_source | implementation_target | test_target | status |
|---|---|---|---|---|---|---|
| `N6UI-001` | N6 UI must present user-understandable signals, cards, queues, status, lineage, and audit context. | All N6 pages | `user_signal_projection`, `user_signal_card`, `user_notification_queue` | N6 UI All N6 pages | UI smoke shows cards/queues/status without raw tables | `planned` |
| `N6UI-002` | N6 UI must not recompute N3/N4/N5 facts, directly pull market data, or replace N5 market-action decisions. | All N6 pages | N6 projection rows, reviewed artifacts | N6 UI All N6 pages | Static/read-only boundary test: no N3/N4/N5 recompute or market pull calls | `doc` |
| `N6UI-003` | N6 UI must read only N6 projection/card/queue rows and reviewed N4/N5/N6 artifacts by default. | N6 repository layer | N6 projection/card/queue, N4/N5/N6 artifacts | N6 UI N6 repository layer | Repository tests only query allowed sources | `gap` |
| `N6UI-004` | Dashboard must show today signal count. | Dashboard metric tile | `user_signal_card` or N6 report artifact | N6 UI Dashboard metric tile | Dashboard today signal count test | `planned` |
| `N6UI-005` | Dashboard must show ActionBlocked count. | Dashboard metric tile | `user_signal_card.action_state`, `user_signal_projection.action_state` | N6 UI Dashboard metric tile | Dashboard ActionBlocked count test | `planned` |
| `N6UI-006` | Dashboard must show ActionExecuted count. | Dashboard metric tile | `user_signal_card.action_state`, `user_signal_projection.action_state` | N6 UI Dashboard metric tile | Dashboard ActionExecuted count test | `planned` |
| `N6UI-007` | Dashboard must show queued_only count. | Dashboard metric tile | `user_notification_queue.queue_status` | N6 UI Dashboard metric tile | Dashboard queued_only count test | `planned` |
| `N6UI-008` | Dashboard must show pending delivery count. | Dashboard metric tile | `user_notification_queue.queue_status`, `user_notification_queue.notification_source` | N6 UI Dashboard metric tile | Dashboard pending delivery count test | `planned` |
| `N6UI-009` | Dashboard must show rollback_safe count or status. | Dashboard metric tile | N6 run/report artifact, rollback artifact path | N6 UI Dashboard metric tile | Dashboard rollback_safe display test | `planned` |
| `N6UI-010` | Dashboard must show latest run_id. | Dashboard run header | `user_projection_run.user_projection_run_id` | N6 UI Dashboard run header | Dashboard latest run_id test | `planned` |
| `N6UI-011` | Signal List must include trade_date, identity_key, and asset_kind. | Signal List table | `user_signal_card`, `user_signal_projection` | N6 UI Signal List table | Table renders trade_date, identity_key, asset_kind | `gap` |
| `N6UI-012` | Signal List must include signal_type, action_state, and action_mark. | Signal List table | `user_signal_card`, `user_signal_projection` | N6 UI Signal List table | Table renders signal_type, action_state, action_mark | `gap` |
| `N6UI-013` | Signal List must include blocked_reason. | Signal List table | `user_signal_card.card_payload_json`, `user_signal_projection.trace_json` when projected | N6 UI Signal List table | Table renders blocked_reason | `gap` |
| `N6UI-014` | Signal List must include trigger_kind, original_condition_key, primary_trigger_period, and trigger_time. | Signal List table | N6 projected payload/context fields | N6 UI Signal List table | Table renders trigger_kind, original_condition_key, primary_trigger_period, trigger_time | `gap` |
| `N6UI-015` | Signal List must include queue_status and source_action_run_id. | Signal List table | `user_notification_queue.queue_status`, `source_action_run_id` | N6 UI Signal List table | Table renders queue_status and source_action_run_id | `gap` |
| `N6UI-016` | Signal List must support filters for trade_date, asset_kind, signal_type, action_state, and blocked_reason. | Signal List filters | N6 card/projection fields | N6 UI Signal List filters | Filters apply trade_date, asset_kind, signal_type, action_state, blocked_reason | `gap` |
| `N6UI-017` | Signal List must support opening Signal Detail, viewing lineage, and exporting the current filtered list. | Signal List actions | Current filtered N6 rows | N6 UI Signal List actions | Open detail, lineage navigation, export filtered list tests | `gap` |
| `N6UI-018` | Signal Detail must show N4 lineage, N5 lineage, and N6 lineage. | Signal Detail lineage sections | N4/N5/N6 report artifacts, N6 rows | N6 UI Signal Detail lineage sections | Detail renders N4/N5/N6 lineage | `gap` |
| `N6UI-019` | Signal Detail must show run_id, event_id, rollback_safe, source artifacts, and rollback SQL. | Signal Detail audit summary | `run_id`, `event_id`, artifacts, rollback SQL | N6 UI Signal Detail audit summary | Detail renders run_id, event_id, rollback_safe, source artifacts, rollback SQL | `gap` |
| `N6UI-020` | ActionBlocked Card title must be exactly "市场动作未确认". | ActionBlocked Card | `user_signal_card.action_state=blocked` | N6 UI ActionBlocked Card | Exact title assertion: 市场动作未确认 | `gap` |
| `N6UI-021` | ActionBlocked Card must not use the wording "交易失败". | ActionBlocked Card | Rendered card text | N6 UI ActionBlocked Card | Negative wording assertion: no 交易失败 | `gap` |
| `N6UI-022` | ActionBlocked Card may show only approved N5 market blocked_reason values. | ActionBlocked Card | N5 projected blocked_reason | N6 UI ActionBlocked Card | Approved blocked_reason allowlist test | `gap` |
| `N6UI-023` | ActionBlocked Card must not show user-layer reasons such as cash, position, T+1, already sold, limits, or blacklist. | ActionBlocked Card | Rendered card reason text | N6 UI ActionBlocked Card | Forbidden user-layer reason denylist test | `gap` |
| `N6UI-024` | ActionBlocked Card must not imply trade, sim, position, or account failure. | ActionBlocked Card | Rendered card text | N6 UI ActionBlocked Card | No trade/sim/position/account failure implication test | `gap` |
| `N6UI-025` | ActionExecuted Card must show "市场动作确认成立". | ActionExecuted Card | `user_signal_card.action_state=executed` | N6 UI ActionExecuted Card | Exact text assertion: 市场动作确认成立 | `gap` |
| `N6UI-026` | ActionExecuted Card must not use "已成交", "已下单", or "已交易". | ActionExecuted Card | Rendered card text | N6 UI ActionExecuted Card | Negative wording assertion: no 已成交/已下单/已交易 | `gap` |
| `N6UI-027` | ActionExecuted Card must not imply sim, real order, filled trade, position mutation, or cash mutation. | ActionExecuted Card | Rendered card text | N6 UI ActionExecuted Card | No sim/order/fill/position/cash implication test | `gap` |
| `N6UI-028` | Notification Preview must show queued_only, preview, and delivered states. | Notification Preview | `user_notification_queue.queue_status` | N6 UI Notification Preview | queued_only/preview/delivered state rendering test | `planned` |
| `N6UI-029` | Notification Preview must not imply provider delivery, push, voice, mobile, or acknowledgement unless a later gate writes that state. | Notification Preview | `user_notification_queue.notification_payload_json` | N6 UI Notification Preview | Preview does not imply provider delivery/push/voice/mobile/ack | `planned` |
| `N6UI-030` | Notification Preview must show only sanitized provider-visible payload. | Notification Preview | sanitized `notification_payload_json` | N6 UI Notification Preview | Forbidden payload keys absent from UI preview | `planned` |
| `N6UI-031` | Audit Panel must show run_id, rollback SQL, rollback_safe, artifact links, source_action_run_id, and source event_id. | Audit Panel | N6 rows, N4/N5/N6 artifacts, rollback SQL paths | N6 UI Audit Panel | Audit fields render test | `gap` |
| `N6UI-032` | Audit Panel must never execute rollback or mutation actions. | Audit Panel | UI route/action set | N6 UI Audit Panel | No rollback execution control test | `doc` |
| `N6UI-033` | Default UI must disable delivery, push, voice, mobile, sim, position, and real trade entrypoints. | Disabled placeholders | UI state only | N6 UI Disabled placeholders | Disabled delivery/push/voice/mobile/sim/position/real trade controls test | `gap` |
| `N6UI-034` | Any real side effect must require a separate reviewed gate. | All N6 pages | Gate artifacts | N6 UI All N6 pages | Static route/action test: no real side-effect endpoints without gate | `doc` |
| `N6UI-035` | Status labels must include blocked, executed, eligible, skipped, queued_only, preview, delivered, rollback_safe, stale_artifact, and superseded. | Shared status label component | N6 card/queue/run status fields | N6 UI Shared status label component | Label set includes all required status labels | `planned` |
| `N6UI-036` | Status colors must reinforce text labels and must not replace readable text. | Shared status label component | Rendered status labels | N6 UI Shared status label component | Text remains visible independent of color | `planned` |
| `N6UI-037` | ActionEligible must be displayed as a watch candidate, not as a buy instruction. | ActionEligible display | `action_state=eligible` | N6 UI ActionEligible display | Eligible rendered as watch candidate, not buy instruction | `gap` |
| `N6UI-038` | ActionSkipped must be displayed as informational skipped/expired state, not as a system error. | ActionSkipped display | `action_state=skipped` or expired context | N6 UI ActionSkipped display | Skipped rendered informational, not system error | `gap` |
| `N6UI-039` | stale_artifact must mean the displayed artifact is older than the selected or latest run context. | Artifact status label | Artifact timestamp/run comparison | N6 UI Artifact status label | stale_artifact label test | `planned` |
| `N6UI-040` | superseded must mean a run or artifact was replaced by a newer reviewed run, not deleted. | Artifact status label | Run supersede metadata/artifact status | N6 UI Artifact status label | superseded label test | `planned` |
| `N6UI-041` | UI tests must assert ActionBlocked and ActionExecuted wording boundaries. | UI wording tests | Rendered ActionBlocked/ActionExecuted cards | N6 UI UI wording tests | Test suite contains exact and forbidden wording assertions | `gap` |
| `N6UI-042` | UI tests must assert read-only boundaries and forbidden side effects. | UI boundary tests | Route map/repository calls/action handlers | N6 UI UI boundary tests | Test suite asserts read-only and forbidden side-effect boundaries | `gap` |

## B. Coverage

```text
rule_count=42
traceability_coverage=42/42
duplicate_count=0
missing_count=0
unresolved_marker_count=0
status_counts={'doc': 3, 'gap': 24, 'planned': 15}
```

## C. Gap Section

| gap_id | status | description | impact | recommendation |
|---|---|---|---|---|
| `N6UI-001` | `planned` | N6 UI must present user-understandable signals, cards, queues, status, lineage, and audit context. | All N6 pages 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 All N6 pages 的只读展示证据和测试。 |
| `N6UI-003` | `gap` | N6 UI must read only N6 projection/card/queue rows and reviewed N4/N5/N6 artifacts by default. | N6 repository layer 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 N6 repository layer，并用 traceability test 覆盖 2 Data Sources。 |
| `N6UI-004` | `planned` | Dashboard must show today signal count. | Dashboard metric tile 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Dashboard metric tile 的只读展示证据和测试。 |
| `N6UI-005` | `planned` | Dashboard must show ActionBlocked count. | Dashboard metric tile 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Dashboard metric tile 的只读展示证据和测试。 |
| `N6UI-006` | `planned` | Dashboard must show ActionExecuted count. | Dashboard metric tile 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Dashboard metric tile 的只读展示证据和测试。 |
| `N6UI-007` | `planned` | Dashboard must show queued_only count. | Dashboard metric tile 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Dashboard metric tile 的只读展示证据和测试。 |
| `N6UI-008` | `planned` | Dashboard must show pending delivery count. | Dashboard metric tile 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Dashboard metric tile 的只读展示证据和测试。 |
| `N6UI-009` | `planned` | Dashboard must show rollback_safe count or status. | Dashboard metric tile 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Dashboard metric tile 的只读展示证据和测试。 |
| `N6UI-010` | `planned` | Dashboard must show latest run_id. | Dashboard run header 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Dashboard run header 的只读展示证据和测试。 |
| `N6UI-011` | `gap` | Signal List must include trade_date, identity_key, and asset_kind. | Signal List table 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 Signal List table，并用 traceability test 覆盖 3.2 Signal List。 |
| `N6UI-012` | `gap` | Signal List must include signal_type, action_state, and action_mark. | Signal List table 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 Signal List table，并用 traceability test 覆盖 3.2 Signal List。 |
| `N6UI-013` | `gap` | Signal List must include blocked_reason. | Signal List table 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 Signal List table，并用 traceability test 覆盖 3.2 Signal List。 |
| `N6UI-014` | `gap` | Signal List must include trigger_kind, original_condition_key, primary_trigger_period, and trigger_time. | Signal List table 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 Signal List table，并用 traceability test 覆盖 3.2 Signal List。 |
| `N6UI-015` | `gap` | Signal List must include queue_status and source_action_run_id. | Signal List table 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 Signal List table，并用 traceability test 覆盖 3.2 Signal List。 |
| `N6UI-016` | `gap` | Signal List must support filters for trade_date, asset_kind, signal_type, action_state, and blocked_reason. | Signal List filters 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 Signal List filters，并用 traceability test 覆盖 3.2 Signal List。 |
| `N6UI-017` | `gap` | Signal List must support opening Signal Detail, viewing lineage, and exporting the current filtered list. | Signal List actions 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 Signal List actions，并用 traceability test 覆盖 3.2 Signal List。 |
| `N6UI-018` | `gap` | Signal Detail must show N4 lineage, N5 lineage, and N6 lineage. | Signal Detail lineage sections 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 Signal Detail lineage sections，并用 traceability test 覆盖 3.3 Signal Detail。 |
| `N6UI-019` | `gap` | Signal Detail must show run_id, event_id, rollback_safe, source artifacts, and rollback SQL. | Signal Detail audit summary 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 Signal Detail audit summary，并用 traceability test 覆盖 3.3 Signal Detail。 |
| `N6UI-020` | `gap` | ActionBlocked Card title must be exactly "市场动作未确认". | ActionBlocked Card 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 ActionBlocked Card，并用 traceability test 覆盖 3.4 ActionBlocked Card。 |
| `N6UI-021` | `gap` | ActionBlocked Card must not use the wording "交易失败". | ActionBlocked Card 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 ActionBlocked Card，并用 traceability test 覆盖 3.4 ActionBlocked Card。 |
| `N6UI-022` | `gap` | ActionBlocked Card may show only approved N5 market blocked_reason values. | ActionBlocked Card 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 ActionBlocked Card，并用 traceability test 覆盖 3.4 ActionBlocked Card。 |
| `N6UI-023` | `gap` | ActionBlocked Card must not show user-layer reasons such as cash, position, T+1, already sold, limits, or blacklist. | ActionBlocked Card 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 ActionBlocked Card，并用 traceability test 覆盖 3.4 ActionBlocked Card。 |
| `N6UI-024` | `gap` | ActionBlocked Card must not imply trade, sim, position, or account failure. | ActionBlocked Card 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 ActionBlocked Card，并用 traceability test 覆盖 3.4 ActionBlocked Card。 |
| `N6UI-025` | `gap` | ActionExecuted Card must show "市场动作确认成立". | ActionExecuted Card 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 ActionExecuted Card，并用 traceability test 覆盖 3.5 ActionExecuted Card。 |
| `N6UI-026` | `gap` | ActionExecuted Card must not use "已成交", "已下单", or "已交易". | ActionExecuted Card 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 ActionExecuted Card，并用 traceability test 覆盖 3.5 ActionExecuted Card。 |
| `N6UI-027` | `gap` | ActionExecuted Card must not imply sim, real order, filled trade, position mutation, or cash mutation. | ActionExecuted Card 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 ActionExecuted Card，并用 traceability test 覆盖 3.5 ActionExecuted Card。 |
| `N6UI-028` | `planned` | Notification Preview must show queued_only, preview, and delivered states. | Notification Preview 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Notification Preview 的只读展示证据和测试。 |
| `N6UI-029` | `planned` | Notification Preview must not imply provider delivery, push, voice, mobile, or acknowledgement unless a later gate writes that state. | Notification Preview 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Notification Preview 的只读展示证据和测试。 |
| `N6UI-030` | `planned` | Notification Preview must show only sanitized provider-visible payload. | Notification Preview 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Notification Preview 的只读展示证据和测试。 |
| `N6UI-031` | `gap` | Audit Panel must show run_id, rollback SQL, rollback_safe, artifact links, source_action_run_id, and source event_id. | Audit Panel 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 Audit Panel，并用 traceability test 覆盖 3.7 Audit Panel。 |
| `N6UI-033` | `gap` | Default UI must disable delivery, push, voice, mobile, sim, position, and real trade entrypoints. | Disabled placeholders 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 Disabled placeholders，并用 traceability test 覆盖 3.8 Disabled Future Entrypoints。 |
| `N6UI-035` | `planned` | Status labels must include blocked, executed, eligible, skipped, queued_only, preview, delivered, rollback_safe, stale_artifact, and superseded. | Shared status label component 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Shared status label component 的只读展示证据和测试。 |
| `N6UI-036` | `planned` | Status colors must reinforce text labels and must not replace readable text. | Shared status label component 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Shared status label component 的只读展示证据和测试。 |
| `N6UI-037` | `gap` | ActionEligible must be displayed as a watch candidate, not as a buy instruction. | ActionEligible display 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 ActionEligible display，并用 traceability test 覆盖 4 Status Labels and Colors。 |
| `N6UI-038` | `gap` | ActionSkipped must be displayed as informational skipped/expired state, not as a system error. | ActionSkipped display 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 ActionSkipped display，并用 traceability test 覆盖 4 Status Labels and Colors。 |
| `N6UI-039` | `planned` | stale_artifact must mean the displayed artifact is older than the selected or latest run context. | Artifact status label 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Artifact status label 的只读展示证据和测试。 |
| `N6UI-040` | `planned` | superseded must mean a run or artifact was replaced by a newer reviewed run, not deleted. | Artifact status label 是已规划能力，尚未形成 implementation/test pass 证据。 | 在 N6-UI dry-run/preview gate 中物化 Artifact status label 的只读展示证据和测试。 |
| `N6UI-041` | `gap` | UI tests must assert ActionBlocked and ActionExecuted wording boundaries. | UI wording tests 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 UI wording tests，并用 traceability test 覆盖 6 Implementation Rules。 |
| `N6UI-042` | `gap` | UI tests must assert read-only boundaries and forbidden side effects. | UI boundary tests 当前尚不能证明满足冻结规则，进入 UI implementation 前必须补实现或测试。 | 在 N6-UI implementation gate 中优先实现 UI boundary tests，并用 traceability test 覆盖 6 Implementation Rules。 |

## D. Artifact Notes

| Artifact | Current completion | Evidence |
|---|---|---|
| Dashboard | `planned` | N6UI-004..N6UI-010 planned; 20260603 read-only lineage dashboard artifact exists, but product UI metrics are not normalized to v1 yet. |
| Signal List | `gap` | N6UI-011..N6UI-017 are gap; required columns, filters, detail navigation, lineage, and export need implementation/tests. |
| Signal Detail | `gap` | N6UI-018..N6UI-019 are gap; lineage sections, artifact links, rollback_safe, event_id, and rollback SQL display need implementation/tests. |
| ActionBlocked | `gap` | N6UI-020..N6UI-024 are gap; exact title, forbidden wording, reason allowlist/denylist, and no trade/account-failure implication tests are required. |
| ActionExecuted | `gap` | N6UI-025..N6UI-027 are gap; exact text and no order/fill/position/cash implication tests are required. |
| Notification Preview | `planned` | N6UI-028..N6UI-030 planned; delivery noop preview materialization runner exists and was rolled back, UI preview rendering and sanitized payload tests remain. |
| Audit Panel | `gap` | N6UI-031 is gap and N6UI-032 is doc; audit fields must render while rollback/mutation controls remain absent. |

## E. Next Steps

1. `N6_USER_INTERFACE_SPEC_v1_IMPLEMENTATION_GATE` - implement read-only N6 UI repository/components/routes/tests from the frozen rules.
2. `N6_USER_INTERFACE_SPEC_v1_DRY_RUN_GATE` - run UI/data dry-run without DB writes, outbox consumption, workers, or side effects.
3. `N6_USER_INTERFACE_SPEC_v1_PREVIEW_GATE` - review dashboard/list/detail/card/notification/audit preview against traceability and wording/safety tests.

## Boundary

```text
code_changed=false
database_written=false
execute_ran=false
outbox_consumed=false
worker_started=false
delivery_push_voice_mobile_sim_position_real_trade=false
```
