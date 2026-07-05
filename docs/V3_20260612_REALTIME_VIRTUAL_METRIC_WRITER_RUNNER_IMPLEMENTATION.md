# V3 20260612 Realtime Virtual Metric Writer Runner Implementation

Result: IMPLEMENTATION_PASS

This gate implemented the bounded N3 writer/runner for the new 20260612
realtime virtual metric route. It did not execute business writes.

## Files

- `src/ashare_v3/market/v3_realtime_virtual_metric_writer.py`
- `scripts/run_v3_realtime_virtual_metric_writer_once.py`
- `tests/test_v3_realtime_virtual_metric_writer_runner.py`

## Runner Behavior

- Default mode is `PLAN_ONLY`.
- Execute requires both `--execute` and `--user-confirmed`.
- Execute also requires an approved `--source-payload-path`.
- Missing flags block before writer invocation.
- Source payload inputs are `candidates`, retained `source_records`, and
  `higher_period_context`.
- Rows are written by asset family into the existing
  `stock/index/board_action_confirmation_projection_metric` tables.
- Realtime virtual metric columns use PostgreSQL lowercase identifiers such as
  `current_d_body_high`; uppercase `D/W/M/Q/Y` names remain display aliases.

## Expected Contract

```text
target_run_id=action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1
expected rows total=100
B_BUY=76
S_SELL=24
metric_ready=100
metric_not_ready=0
```

## Boundary

```text
database_written=false
business_data_written=false
rollback_executed=false
scheduler_started_or_modified=false
wrapper_or_n3_n4_n5_executed=false
outbox_inbox_checkpoint_consumed_or_updated=false
n6_voice_mobile_sim_trade_entered=false
old_system_touched=false
```

## Remaining Execute Prerequisite

The runner is implemented, but execute is not ready in this gate. The next
required step is an approved source payload contract/preflight gate:

```text
V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_PAYLOAD_CONTRACT_PREFLIGHT_GATE
```
