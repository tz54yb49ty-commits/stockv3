# N5 Action Confirmation 20260608 v13 Index-All Until 09:52 v4 Repair Retry Rollback Report

Result: **ROLLBACK_PASS**

This gate executed the user-confirmed scoped N5 rollback SQL. It only removed the eligibility-only N5 retry lineage for the target action run. It did not execute N4 or N3 rollback, did not run metric-aware N5, did not consume or update N4 outbox, did not enter N6, did not start a worker, and did not touch the old system.

## Target

```text
action_run_id=action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry
source_trigger_run_id=trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry
consumer_name=n5_action_consumer_v1
rollback_sql=sql/N5_action_confirmation_20260608_v13_index_all_until_0952_v4_repair_retry_rollback.sql
target_db=ashare_v3 / ashare_v3_user / 127.0.0.1:5432
```

## Precheck Proof

```text
final_gate_result=PASS
rollback_sql_guard_repair=REPAIR_PASS
hard-fail before first DELETE/UPDATE=true
fixed guard no longer blocks preserved N4_trigger outbox=true
N5 outbox delivered/delivering=0/0
downstream refs to N5 outbox/action_run_id=0
N6 scoped rows=0
N6/user/sim/position/order/trade refs=0
```

Live scoped rows before rollback:

```text
common_action_run=1/status=passed
common_action_quality_item=3801
stock/index/board_action_fact=113/6/0
common_action_event=119
N5 common_event_outbox=119
N5 common_event_inbox=3920
N5 consumer checkpoint refs=1997
```

## Executed Command

```text
/opt/homebrew/opt/postgresql@16/bin/psql "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3" -v ON_ERROR_STOP=1 -f sql/N5_action_confirmation_20260608_v13_index_all_until_0952_v4_repair_retry_rollback.sql
```

Execution result:

```text
sql_exit_code=0
transaction_committed=true
hard_fail_guard_passed=true
metric_aware_n5_rerun_executed=false
```

## Deleted Rows

```text
common_event_consumer_checkpoint=1997
common_event_inbox=3920
common_event_outbox=119
common_action_event=119
board_action_fact=0
index_action_fact=6
stock_action_fact=113
common_action_quality_item=3801
common_action_run=1
```

## Live Post-Check Proof

Scoped N5 rows are cleared:

```text
common_action_run=0
common_action_quality_item=0
stock/index/board_action_fact=0/0/0
common_action_event=0
N5 common_event_outbox=0
N5 common_event_inbox=0
N5 consumer checkpoint refs=0
downstream inbox refs=0
```

## N4 Preservation Proof

N4 trigger facts and N4 outbox status were preserved:

```text
common_trigger_match=119
common_trigger_state=3920
TriggerMatched pending=119
TriggerPendingMarketData pending=3801
N4 outbox delivered/delivering=0/0
N4 outbox status updated=false
N4 trigger facts modified=false
```

## N3 Metric Preservation Proof

N3 action-confirmation metric facts were preserved:

```text
metric_run_id=action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry
metric_run=1/status=passed
stock/index/board metric rows=113/6/0
N3 metric modified=false
```

## Downstream And Forbidden Scope Proof

```text
user_projection_run refs=0
user_signal_projection refs=0
user_signal_card refs=0
position_state/event refs=0/0
N4 rollback executed=false
N3 rollback executed=false
N4 outbox consumed/updated=false
worker_started=false
entered_N6=false
delivery/push/voice/mobile=false
sim/position/pnl/real_trade=false
proposal/order/trade=false
old_system_touched=false
```

## Validation

```text
post_check_sql_exit_code=0
JSON parse=required
git diff --check=required
```

## Decision

Allow returning to runtime_control for:

```text
N5 rollback post-review gate
```

Metric-aware N5 rerun is now unblocked from the N5 rollback side, but it must still be opened as a separate final-gated N5 action execute/dry-run flow. This rollback gate did not run metric-aware N5.
