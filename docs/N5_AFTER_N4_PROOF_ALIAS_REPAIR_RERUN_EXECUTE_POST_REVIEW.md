# N5 After N4 Proof Alias Repair Rerun Execute Post-Review

Result: `EXECUTE_PASS_DOWNSTREAM_DEFERRED`

Executed scope:

- `action_run_id=action_consumer_execute_20260617_after_n4_proof_alias_repair_rerun__trigger_action_confirmation_metric_execute_20260617_full_day_proof_alias_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- `source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_full_day_proof_alias_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- `consumer_name=n5_action_consumer_v1`
- source event type: `TriggerMatched`
- read/consumed count: `550`

Persisted rows:

- `common_action_run=1`
- `stock_action_fact=482`
- `index_action_fact=19`
- `board_action_fact=49`
- `common_action_event=550`
- `common_action_tracking_state=550`
- N5 `common_event_outbox=550`
- scoped N4 `common_event_inbox=550`
- scoped N4 consumer checkpoints `544`

Distributions:

- action state: `blocked=547`, `executed=3`
- action event: `ActionBlocked=547`, `ActionExecuted=3`
- final action mark: `30m_volume=3`, `null=547`
- runtime signal type: `B_BUY=200`, `S_SELL=350`
- HINT trace preserved: `BUY_HINT=18`, `SELL_HINT=3`; no HINT runtime signal type.

No-action proof:

- N5 action events/facts only reference N4 `TriggerMatched=550`.
- `TriggerPendingMarketData` inbox/action-event refs: `0`.
- `TriggerStateChanged` inbox/action-event refs: `0`.

Boundary proof:

- N4 source outbox remains pending-only: `TriggerMatched=550`, `TriggerPendingMarketData=3776`, `TriggerStateChanged=4326`.
- N4 outbox delivered/delivering: `0`.
- N5 outbox remains pending-only: `ActionBlocked=547`, `ActionExecuted=3`.
- N5 outbox delivered/delivering: `0`; downstream N5 outbox inbox/checkpoint refs: `0`.
- N6/user/voice/mobile/sim/position/order/real-trade refs: `0`.
- No worker/scheduler started; old system not touched.

Artifacts:

- execute report: `docs/N5_AFTER_N4_PROOF_ALIAS_REPAIR_RERUN_EXECUTE_REPORT.json`
- post-review JSON: `docs/N5_AFTER_N4_PROOF_ALIAS_REPAIR_RERUN_EXECUTE_POST_REVIEW.json`
- rollback SQL: `sql/N5_20260617_after_n4_proof_alias_repair_rerun_rollback.sql`

N6 remains deferred; no N6 execute prompt is emitted by this gate.
