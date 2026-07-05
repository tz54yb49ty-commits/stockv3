# N5 After N4 Proof Alias Repair Rerun Preflight

Result: `N5_PREFLIGHT_PASS`

Scope:

- `source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_full_day_proof_alias_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- planned `action_run_id=action_consumer_execute_20260617_after_n4_proof_alias_repair_rerun__trigger_action_confirmation_metric_execute_20260617_full_day_proof_alias_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- `consumer_name=n5_action_consumer_v1`

Proof:

- N4 post-review is `N4_RERUN_PASS`; DB trigger run status is `passed`, `p0=0`.
- Existing N5 refs for this source are all `0`.
- N4 outbox is pending-only: `TriggerMatched=550`, `TriggerPendingMarketData=3776`, `TriggerStateChanged=4326`; delivered/delivering is `0`.
- N5 entry scope is only `TriggerMatched=550`.
- `TriggerMatched` dry-run plans `550` action facts: `stock=482`, `index=19`, `board=49`.
- planned events: `ActionBlocked=547`, `ActionExecuted=3`.
- planned final action marks: `30m_volume=3`, `null=547`.
- `TriggerPendingMarketData=3776` is quality-only/no-action: action facts/events/outbox `0`.
- `TriggerStateChanged=4326` is state-gate-only/no-action: action facts/events/outbox `0`.
- Non-entry events have `common_trigger_match_refs=0`, `writes_common_trigger_match_true=0`, `is_n5_action_entry_true=0`.
- N3 metric join is complete: `matched_rows=550`, `joined_rows=550`, `missing_rows=0`; opaque payload action-confirmation is not trusted.
- Final `action_mark` is from N5/N3 metric confirmation only, not condition key/original condition key/required periods.
- Runtime signal types are only `B_BUY/S_SELL`; HINT remains trace: `BUY_HINT=18`, `SELL_HINT=3`.

Rollback SQL:

- `sql/N5_20260617_after_n4_proof_alias_repair_rerun_rollback.sql`

Forbidden scope proof:

- N5 runtime was not executed.
- N6 was not entered.
- N4 outbox was not consumed or updated.
- N5 outbox was not consumed.
- No worker/scheduler was started.
- No N1/N2/N3/N4 mutation was performed.
- No voice/mobile/sim/position/order/real trade or old system was touched.

Allowed next prompt:

```text
layer_role=N5_action. Enter N5_AFTER_N4_PROOF_ALIAS_REPAIR_RERUN_EXECUTE. Use trade_date=20260617; action_run_id=action_consumer_execute_20260617_after_n4_proof_alias_repair_rerun__trigger_action_confirmation_metric_execute_20260617_full_day_proof_alias_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1; source_trigger_run_id=trigger_action_confirmation_metric_execute_20260617_full_day_proof_alias_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1; source_metric_run_id=action_confirmation_projection_metric_20260617_full_day__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1; source_condition_run_id=condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1; consumer_name=n5_action_consumer_v1; source_event_type=TriggerMatched; expected_read_event_count=550; n5_preflight_artifact=docs/N5_AFTER_N4_PROOF_ALIAS_REPAIR_RERUN_PREFLIGHT.json; n5_baseline_artifact=docs/N5_AFTER_N4_PROOF_ALIAS_REPAIR_RERUN_PREFLIGHT.json; rollback_sql_path=sql/N5_20260617_after_n4_proof_alias_repair_rerun_rollback.sql. Execute N5 action run-once only. Do not enter N6. Do not consume N5 outbox. Do not update N4 outbox status. Do not start worker/scheduler. Do not touch N1/N2/N3/N4 writes. Do not touch voice/mobile/sim/position/order/real trade. Do not read or modify old system.
```
