# N5 Action Pipeline Artifact Baseline Reconciliation Report

- result: `RECONCILED`
- layer_role: `N5_action`
- gate: `N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_GATE`

## Root Cause

- N1N5-P0-001: The execute report embedded dry_run_plan baseline diagnostics that treated docs/N5_ACTION_PIPELINE_EXECUTE_CONTRACT.json as an N5-1 baseline, producing baseline_read_event_count=0 and a nested failed P0 even though the reviewed execute contract expected 605 and top-level execute quality was 0/0/0.
- N1N5-P1-002: Checkpoint counts mixed accepted event/checkpoint plan entries with physical common_event_consumer_checkpoint watermark rows. Live scoped watermark refs are 73 while accepted/inbox events are 605.

## Baseline Semantics

- baseline_kind: `N5_action_pipeline_execute_contract`
- baseline_read_event_count: `605`
- current_read_event_count: `605`
- read_event_count_delta: `0`
- explainable: `True`
- explanation: N5 action pipeline read_event_count and distributions match the reviewed execute contract; previous baseline_read_event_count=0 was caused by treating the execute contract as an N5-1 baseline.

## Checkpoint Semantics

- accepted_event_count: `605`
- common_event_inbox_rows: `605`
- checkpoint_plan_entry_count: `605`
- checkpoint_physical_watermark_rows: `73`
- live_checkpoint_ref_rows: `73`
- checkpoint_key: `consumer_name + partition_key + source_layer`
- meaning: 605 accepted N4 events were inserted into inbox; checkpoint stores/upserts partition watermark rows and live scoped refs are 73.

## Live DB Proof

- common_action_run: `1`
- common_action_event: `605`
- common_event_outbox_n5: `605`
- common_event_inbox_n5_consumer: `605`
- common_event_consumer_checkpoint_scoped_refs: `73`
- n4_outbox_trigger_matched_pending: `605`
- n6_downstream_refs: `0`

## Modified Files

- `docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.json`
- `docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.md`
- `docs/N5_ACTION_PIPELINE_EXECUTE_CONTRACT.json`
- `docs/N5_ACTION_PIPELINE_EXECUTE_CONTRACT.md`
- `docs/N5_ACTION_PIPELINE_EXECUTE_PREFLIGHT.json`
- `docs/N5_ACTION_PIPELINE_EXECUTE_PREFLIGHT.md`
- `docs/N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_REPORT.json`
- `docs/N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_REPORT.md`
- `src/ashare_v3/action/run_once_dry_run.py`
- `src/ashare_v3/action/execute.py`
- `tests/test_action_execute.py`

## Forbidden Scope Proof

- execute_performed_in_this_gate: `False`
- database_written_in_this_gate: `False`
- outbox_consumed_or_updated: `False`
- worker_started: `False`
- n6_entered: `False`
- rollback_executed: `False`
- proposal_order_trade_touched: `False`
- position_pnl_real_trade_touched: `False`

## Next Gate

`runtime_control rerun N1_N5 cross-layer audit or proceed with remaining N4-owned blockers`

## Validation

- JSON parse: `PASS`
- targeted tests: `PASS (tests/test_action_execute.py, 32 tests)`
- compileall: `PASS`
- git diff --check: `PASS`
