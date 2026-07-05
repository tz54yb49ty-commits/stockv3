# N5 20260702 Raw Prevday C1 Superseded Closeout Registration

## READ_ONLY_PREFLIGHT

- `layer_role=N5_action`
- This registration is N5-only documentation.
- No DB write was performed by this registration.
- No N3/N4/N6 runtime was executed.
- No market data was pulled.
- No launchd, schema, rollback, or commit action was performed.

## CLOSEOUT SUMMARY

The corrected superseding N5 live tracking run is the current N5 source for N6:

```text
source_action_run_id =
n5_live_tracking_20260702__trigger_provisional_ordinary_20260702_until_0944__realtime_action_confirmation_metric_20260702_until_0944__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__atomic_rule_v1_period_rollover_guard_v1__raw_prevday_c1_amount_v1
```

N5 outbox for this run contains only:

```text
ActionEligible:pending = 60
ActionExecuted:pending = 4
```

The corrected `stock:SZ:002493` `ActionExecuted` row has:

```text
action_mark = 30m_volume
action_mark_reason = buy_30m_virtual_amount_expanded
source_metric_run_id = n3t_action_confirmation_metric_20260702_until_0944__n5_live_tracking_scope_v1_raw_prevday_c1_amount_v1
previous_day_same_window_amount = 100271508.75
current_30m_virtual_amount = 144198035
```

## DB EVIDENCE

Read-only DB evidence for the superseding N5 run:

| Area | Value |
|---|---|
| `common_event_outbox` | `ActionEligible:pending=60`, `ActionExecuted:pending=4` |
| `common_action_tracking_state` | `eligible/tracking/pending=56`, `executed/executed/passed=4` |
| `common_event_inbox` | `TriggerMatched:processed=60`, `TriggerStateChanged:processed=30` |
| `common_event_consumer_checkpoint` | `90` rows scoped to the superseding consumer/action run |
| N4 source outbox | `TriggerMatched:pending=60`, `TriggerStateChanged:pending=231` |
| N5 consumed `TriggerStateChanged(trigger_live=true)` | `0` |
| Stale metric refs in superseding N5 run | `0` |

The old N5 run is retained only as historical evidence. Its `stock:SZ:002493`
`ActionExecuted` remains:

```text
action_mark = normal
source_metric_run_id = n3t_action_confirmation_metric_20260702_until_0944__n5_live_tracking_scope_v1_source_close_label_policy_v1
```

## SOURCE SELECTION RULE

N6 must select the corrected superseding `source_action_run_id` above for the
20260702 09:44 raw-prevday-C1 path.

N6 must not select the stale N5 run for this corrected path:

```text
n5_live_tracking_20260702__trigger_provisional_ordinary_20260702_until_0944__realtime_action_confirmation_metric_20260702_until_0944__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__atomic_rule_v1_period_rollover_guard_v1
```

The stale run is read-only. Do not update, delete, rollback, or reinterpret it
inside this closeout registration.

## ROLLBACK READINESS

Rollback was not executed.

If a later explicit rollback gate is authorized, the rollback scope is limited
to:

```text
action_run_id = n5_live_tracking_20260702__trigger_provisional_ordinary_20260702_until_0944__realtime_action_confirmation_metric_20260702_until_0944__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__atomic_rule_v1_period_rollover_guard_v1__raw_prevday_c1_amount_v1
consumer_name = n5_live_tracking_poller_v2_raw_prevday_c1_amount_v1
```

Allowed rollback targets for that future gate:

- `common_event_consumer_checkpoint` by `consumer_name` and `checkpoint_payload.action_run_id`
- `common_event_inbox` by `consumer_name` and `raw_json.action_run_id`
- `common_event_outbox` by `source_layer=N5_action` and `source_run_id=action_run_id`
- `common_action_tracking_state` by `run_id=action_run_id`

Forbidden rollback targets:

- stale N5 action run rows
- N4 `common_event_outbox`
- N3 facts or outbox
- N4 facts
- N6 user projection rows
- launchd
- schema

## REPEATED ONE-SHOT CONTRACT

N5 has no remaining code task for the current 09:44 output. For future minutes,
N5 waits for the next N3T metric run and then repeats:

```text
plan-only preflight -> explicit execute -> post-review
```

Inputs remain:

- N4 pending `TriggerMatched`
- N4 pending `TriggerStateChanged(trigger_live=false)`
- a new N3T metric run with `source_basis=N3T_C1_CLOSED`

Ignored inputs remain:

- `TriggerStateChanged(trigger_live=true)`
- `TriggerPendingMarketData`

N5 output to N6 remains only:

- `ActionEligible`
- `ActionExecuted`

## FINAL VERDICT

```text
N5_RAW_PREVDAY_C1_SUPERSEDED_CLOSEOUT_REGISTRATION_PASS_READY_FOR_N6_EXECUTE_GATE
```
