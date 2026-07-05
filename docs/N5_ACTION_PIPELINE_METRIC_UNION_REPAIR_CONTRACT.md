# N5 Action Pipeline Metric Union Repair Contract

Status: CONTRACT_PASS

## Contract Summary

```text
source_trigger_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
existing_action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
execute_authorized=false
join_policy=deterministic asset_kind + identity_key + trade_date over old metric run UNION latest additive metric run
opaque_action_confirmation_payload_trusted=false
```

## Expected Repair Distribution

```text
planned_events={"ActionBlocked": 604, "ActionExecuted": 1}
blocked_reasons={"amount_confirmation_failed": 17, "metric_missing": 28, "price_confirmation_failed": 559}
```

## Future Repair Scope Candidate

```text
stock/index/board_action_fact
common_action_event
common_event_outbox payload_json/event_type/dedup-compatible fields
```

This contract does not authorize execution. A future execute gate must provide hard-fail rollback SQL, guard delivered/delivering N5 outbox, guard downstream inbox/checkpoint/delivery refs, and coordinate N6 projection/card repair separately.
