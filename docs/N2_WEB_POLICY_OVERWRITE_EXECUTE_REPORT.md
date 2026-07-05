# N2 Web Policy Overwrite Execute Report

```text
result=EXECUTE_PASS
layer_role=N2_condition
run_id=condition_layer_20260528_source_20260528_v6
source_trade_date=20260528
for_trade_date=20260529
prev_trade_date=20260528
policy_hash=ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576
```

## Execution Summary

执行命令：

```bash
PYTHONPATH=src python3 scripts/run_condition_layer_execute.py \
  --source-trade-date 20260528 \
  --policy configs/n2_policy/default_policy_draft.json \
  --run-id condition_layer_20260528_source_20260528_v6 \
  --execute \
  --overwrite \
  --user-confirmed \
  --operator codex \
  --confirmation-note N2-web-policy-active-supersede \
  --report-path docs/N2_web_policy_execute_report.json
```

执行边界：

```text
N2 overwrite executed=true
condition business rows written=true
N3/N4/N5/N6 entered=false
market_data_pulled=false
worker_started=false
rollback_sql_executed=false
outbox/inbox/checkpoint delta=0/0/0
old_system_touched=false
```

## Active Lineage Proof

```text
condition_layer_20260528_source_20260528_v6.status=passed_active
condition_layer_20260528_source_20260528_v5.status=superseded
active passed run count for 20260528 -> 20260529 = 1
P0/P1/P2 = 0/3/3
```

## Row Count Proof

Actual rows match latest gate `expected_rows`:

```text
condition_basis: stock=5506 index=83 board=428
condition_pool: stock=4271 index=169 board=875
minute_target_scope: stock=4251 index=169 board=875
condition_display_basis: stock=2011 index=83 board=428
monitor_target: stock=5506 index=83 board=428
common_condition_quality_item=103
```

## Policy Proof

```text
policy_path=configs/n2_policy/default_policy_draft.json
policy_hash_report=ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576
policy_hash_default=ded5432ff4769260061449f15a2edcc18e4ea3fe3874e26b42287ca1953cb576
policy_hash_matches_default=true
```

## Forbidden Scope Proof

```text
common_event_outbox delta=0
common_event_inbox delta=0
common_event_consumer_checkpoint delta=0
common_market_data_run refs=0
common_trigger_run refs=0
common_action_run refs=0
user_projection_run refs=0
user_signal_projection refs=0
market_data_pulled=false
worker_started=false
migration_performed=false
```

## Rollback Proof

```text
rollback_sql_path=sql/N2_condition_layer_20260528_v6_web_policy_rollback.sql
restore_run_id=condition_layer_20260528_source_20260528_v5
rollback_safe=true
guard outbox/inbox/checkpoint=true
guard N3/N4/N5/N6 refs=true
no CASCADE/DROP/TRUNCATE=true
```

## Next Gate

```text
allow_enter_N2_WEB_POLICY_OVERWRITE_EXECUTE_POST_REVIEW_GATE=true
```
