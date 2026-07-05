# N5 20260605 Action Readiness Dry-Run Gate Report

- result: `DRY_RUN_BLOCKED`
- source_trigger_run_id: `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- action_run_id: `action_consumer_market_action_confirmation_v1_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- N4 outbox status: `{'pending': 1537, 'delivered': 0, 'delivering': 0}`
- N4 by event type: `{'TriggerMatched': 1537}`
- runtime signal distribution: `{'B_BUY': 1286, 'S_SELL': 251}`
- asset distribution: `{'board': 63, 'index': 1, 'stock': 1473}`
- match_basis distribution: `{'intraday_projection': 275, 'realtime_snapshot': 1262}`
- N3 metric expected run: `action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- metric_join_coverage: `0/1537`
- BJ/FULL in TriggerMatched: `BJ=0, FULL=29`
- N5 scoped refs total: `0`
- downstream refs total: `0`
- P0/P1/P2: `2/1/0`

## Blockers
- `P0` `n4_full_trigger_matched_rows_entered_n5_scope` blocked_by_layer=`N4_trigger` count=`29`: FULL rows appear in TriggerMatched despite N4 v4 N5 entry alignment requiring FULL blocked rows not to enter N5.
- `P0` `n3_action_confirmation_metric_missing_for_20260605` blocked_by_layer=`N3_market_data` count=`1537`: No N3 action-confirmation metric rows are present for the expected 20260605 metric run; N5 cannot produce metric-aware dry-run output without trusting opaque payloads.

## Contract Drift

- `P1` `n5_20260605_entry_eligibility_payload_fields_missing`: N4 report says `invalid_n5_entry_count=0`, but current outbox payload has no `action_eligible`, `n5_entry_allowed`, or `outcome_classification` fields. This is not the primary blocker here, but should be refreshed in the N4/N5 contract before execute.

## Dry-Run Decision

Final metric-aware N5 action planning was not finalized because required input contracts are not complete. The report records the 1537 would-consume TriggerMatched rows, but does not convert them into ActionBlocked/ActionExecuted rows without N3 metric facts.

## Boundary

No N5 execute, no N4/N5 outbox consumption or status update, no inbox/checkpoint/action fact/action event/N5 outbox writes, no N6, no worker, no delivery/notification/push/voice/mobile/sim/position/real trade.

## Next Gate

- N5 execute final gate: `not allowed`
- blocked_by_layer=`N3_market_data`: materialize 20260605 N3 action-confirmation metrics after the N4 matched-only run.
- blocked_by_layer=`N4_trigger`: reconcile 29 FULL TriggerMatched rows with N4 v4 N5-entry contract.
