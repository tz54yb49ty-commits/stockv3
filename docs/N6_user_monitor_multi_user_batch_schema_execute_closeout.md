# N6 User Monitor Multi-User Batch Schema Execute Closeout

Gate: `RUNTIME_CONTROL_N6_MONITOR_MULTI_USER_BATCH_SCHEMA_EXECUTE_GATE`

Executed migration:

```text
sql/N6_user_monitor_multi_user_batch_alignment_migration.sql
```

Rollback path, not executed:

```text
sql/N6_user_monitor_multi_user_batch_alignment_rollback.sql
```

Execution result:

```text
returncode=0
duration_ms=154.37
```

Precheck passed:

```text
target_tables=user_monitor_stock,user_monitor_index,user_monitor_board
pre_row_counts={stock:569,index:36,board:382}
duplicate_group_count={stock:0,index:0,board:0}
unbackfillable_user_id_rows={stock:0,index:0,board:0}
```

Post-verify passed:

```text
transaction_read_only=on
row_count_drift={stock:0,index:0,board:0}
null_user_id={stock:0,index:0,board:0}
required_columns_missing=[]
expected_indexes_missing=[]
active_unique_indexes_include_user_and_batch=true
protected_count_drift={user_signal_projection:0,user_signal_card:0,common_event_outbox:0,common_event_inbox:0,common_event_consumer_checkpoint:0}
```

Forbidden side effects were not observed:

```text
n6_runtime_executed=false
n3_n4_n5_worker_mutation=false
signal_card_mutation=false
outbox_inbox_checkpoint_mutation=false
rollback_executed=false
```

Final verdict:

```text
RUNTIME_CONTROL_N6_MONITOR_MULTI_USER_BATCH_SCHEMA_EXECUTE_PASS_READY_FOR_UI_RELOAD_VERIFY_GATE
```
