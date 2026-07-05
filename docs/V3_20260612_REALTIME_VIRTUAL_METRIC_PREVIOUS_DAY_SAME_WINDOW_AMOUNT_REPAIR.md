# V3 20260612 Realtime Virtual Metric Previous-Day Same-Window Amount Repair

Status: REPAIR_PASS

```text
target_run_id=action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1
payload_rows=100
previous_day_same_window_amount_non_null=100
missing_live_schema_column=previous_day_same_window_amount
repair_sql=sql/V3_20260612_realtime_virtual_metric_previous_day_same_window_amount_repair.sql
execute_allowed_now=false
requires_runtime_control_final_gate=true
```

## Scope

- Additive schema/backfill SQL is prepared but not executed.
- Backfill scope is only the target `projection_run_id` rows: stock/index/board = 62/0/38.
- N3 provides metric evidence only; N5 owns final `action_mark` derivation.

## Forbidden Scope

- 不执行 N4/N5。
- 不消费/update outbox/inbox/checkpoint。
- 不进入 N6/voice/mobile/sim/position/order/trade。
- 不启动 scheduler/worker。

## Next

Return to runtime_control for repair execute final gate review.

## Validation

```text
targeted_tests=PASS: 29 tests OK
json_parse=PASS
compileall=PASS
repair_sql_static_check=PASS
forbidden_scope_scan=PASS
git_diff_check=PASS
sql_executed=false
database_written=false
scheduler_started_or_modified=false
```

## Guard Refresh

```text
allow_reviewed_n4_refs=true
allowed_n4_event_types=TriggerMatched/TriggerStateChanged/TriggerPendingMarketData
common_trigger_match_refs=preserved_readonly
N5/N6/user/sim/voice/mobile refs=hard_fail
inbox/checkpoint refs=hard_fail
worker/downstream flags=hard_fail
sql_default_hard_fail=true
```
