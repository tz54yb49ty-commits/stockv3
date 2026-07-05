# N3 -> N4 -> N5 20260602 11:05 Flow Readiness Matrix

## Result

```text
FLOW_PROGRESSING
```

This report is read-only. It does not execute N4 production writes, does not execute N5 production writes, does not enter N6, and does not start a worker.

## Layer Evidence

| Stage | Layer | Status | Evidence |
|---|---|---|---|
| N3-B2 live3 projection | N3_market_data | passed | `docs/N3_B2_20260602_LIVE3_EXECUTE_POST_REVIEW.json` |
| N4 context snapshot | N4_trigger | passed | `docs/N4_20260602_TRIGGER_CONTEXT_SNAPSHOT_EXECUTE_POST_REVIEW.json` |
| N4 projection matcher dry-run | N4_trigger | DRY_RUN_PASS | `docs/N4_20260602_projection_matcher_after_context_execute_dry_run.json` |
| N4 projection matcher execute preflight | N4_trigger | PREFLIGHT_PASS | `docs/N4_20260602_projection_matcher_1105_after_context_execute_preflight.json` |
| N4 projection matcher final gate | N4_trigger | PASS | `docs/N4_20260602_projection_matcher_1105_final_gate.json` |
| N5 mock from N4 preflight | N5_action | DRY_RUN_PASS | `docs/N5_20260602_1105_mock_from_n4_preflight_dry_run.json` |
| N5 live execute preflight | N5_action | BLOCKED as expected | `docs/N5_20260602_1105_live_after_n4_preflight_execute_preflight.json` |

## N4 Current Baseline

```text
n4_context_run_id = trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1
n4_context_status = passed
n4_context_P0/P1/P2 = 0/0/0
stock/index/board context rows = 4715/220/1006

n4_matcher_execute_run_id = trigger_projection_matcher_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
n4_matcher_common_trigger_run_rows = 0
n4_matcher_trigger_state_rows = 0
n4_matcher_trigger_match_rows = 0
n4_matcher_quality_rows = 0
n4_matcher_outbox_rows = 0
```

## N4 Matcher Gate

```text
dry_run_result = DRY_RUN_PASS
dry_run_candidate_count = 5941
dry_run_matched_count = 478
dry_run_pending_count = 3484
dry_run_not_matched_signal_count = 1979
dry_run_P0/P1/P2 = 0/1/0

preflight_result = PREFLIGHT_PASS
accepted_source_event_count = 2487
matched_output_count = 478
pending_output_count = 3484
inbox_write_plan_count = 2487
checkpoint_write_plan_count = 2487
preflight_P0/P1/P2 = 0/0/0
```

## N5 Mock / Dry-Run

Because N4 production outbox is not written yet, N5 used mock N4 outbox rows derived from the N4 execute preflight `trigger_output_plan`.

```text
mocked = true
mock_source = docs/N4_20260602_projection_matcher_1105_after_context_execute_preflight.json
read_event_count = 3962
TriggerMatched = 478
TriggerPendingMarketData = 3484
planned_action_fact_count = 478
quality_plan_only_count = 3484
output_event_plan = ActionEligible:478, ActionBlocked:0, ActionExecuted:0, ActionSkipped:0
P0/P1/P2 = 0/0/0
writes_performed = false
```

## N5 Live Preflight

The live N5 execute preflight reads real N4 outbox rows and is blocked because N4 production execute has not happened.

```text
allow_execute = false
read_event_count = 0
P0/P1/P2 = 2/1/0
P0 reason = N4 production outbox rows are not available yet
```

This is the expected blocker before N4 production confirmation. It is not an N5 logic failure.

## Global Boundary

```text
common_event_outbox = 153828
common_event_inbox = 56170
common_event_consumer_checkpoint = 4368
N4 matcher production rows = 0
N5 target action_run/facts/events = 0
N6 entered = false
worker_started = false
old_system_touched = false
real_trading = false
```

## Next Production Gate

The next required production step is still N4 projection matcher execute. It will write N4 trigger facts, N4 outbox, N4 inbox, and N4 checkpoint rows, so it requires explicit user confirmation.

```bash
PYTHONPATH=src:scripts python3 scripts/run_trigger_projection_matcher_once.py \
  --execute \
  --user-confirmed \
  --execute-run-id trigger_projection_matcher_execute_20260602_1105__condition_layer_20260601_source_20260601_v1 \
  --trigger-context-run-id trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1 \
  --projection-run-id realtime_projection_metric_20260602_live3__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1 \
  --snapshot-run-id realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1 \
  --dry-run-report-path docs/N4_20260602_projection_matcher_after_context_execute_dry_run.json \
  --json-report-path docs/N4_20260602_projection_matcher_1105_execute_report.json \
  --markdown-report-path docs/N4_20260602_PROJECTION_MATCHER_1105_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N4_20260602_projection_matcher_1105_rollback.sql
```

## After N4 Execute

Do only N4 post-review first:

```text
confirm N4 execute status
confirm TriggerMatched = 478
confirm TriggerPendingMarketData = 3484
confirm common_event_inbox / checkpoint writes
confirm N4 outbox pending rows
confirm rollback_safe
stop before N5
```

Then explicitly switch to:

```text
layer_role=N5_action
N5 action consumer 20260602 11:05 live dry-run / execute preflight / execute confirmation
```
