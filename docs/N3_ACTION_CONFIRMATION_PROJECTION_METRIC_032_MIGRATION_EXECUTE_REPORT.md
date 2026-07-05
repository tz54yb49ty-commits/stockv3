# N3 Action-Confirmation Projection Metric 032 Migration Execute Report

Status: EXECUTE_PASS

Generated at: 2026-06-02T05:53:18.916579+00:00

Layer role: N3_market_data

## Executed Command

```text
python3 psycopg equivalent of psql "$ASHARE_V3_RUNTIME_DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/032_n3_action_confirmation_metric_schema.sql
```

`psql` was not available in the current shell and `ASHARE_V3_RUNTIME_DATABASE_URL` was not exported, so the same SQL file was executed with `psycopg` against the project default local v3 runtime DSN after target DB proof.

## Target DB Proof

```text
database=ashare_v3
user=ashare_v3_user
host=127.0.0.1/32
port=5432
base_runtime_tables_exist=True
old_system_db=false
```

## Created Tables

```text
board_action_confirmation_projection_metric
index_action_confirmation_projection_metric
stock_action_confirmation_projection_metric
```

## Created Indexes

```text
count=18
board_action_confirmation_pro_projection_run_id_identity_ke_key
board_action_confirmation_projection_metric_pkey
idx_board_action_confirmation_metric_boundary
idx_board_action_confirmation_metric_run
idx_board_action_confirmation_metric_snapshot
idx_board_action_confirmation_metric_trade_identity
idx_index_action_confirmation_metric_boundary
idx_index_action_confirmation_metric_run
idx_index_action_confirmation_metric_snapshot
idx_index_action_confirmation_metric_trade_identity
index_action_confirmation_pro_projection_run_id_identity_ke_key
index_action_confirmation_projection_metric_pkey
idx_stock_action_confirmation_metric_boundary
idx_stock_action_confirmation_metric_run
idx_stock_action_confirmation_metric_snapshot
idx_stock_action_confirmation_metric_trade_identity
stock_action_confirmation_pro_projection_run_id_identity_ke_key
stock_action_confirmation_projection_metric_pkey
```

## Row Counts

```text
stock=0
index=0
board=0
```

## Event Boundary

```text
common_event_outbox_delta=0
common_event_inbox_delta=0
common_event_consumer_checkpoint_delta=0
```

## Downstream Boundary

```text
N4/N5/N6 downstream row_count_delta_zero=True
checked_tables=32
```

## Rollback

```text
rollback_safe=True
schema_rollback=sql/032_n3_action_confirmation_metric_schema_rollback.sql
business_rollback=sql/N3_action_confirmation_projection_metric_business_rollback.sql
```

## Boundary

No business rows were written. No market data was pulled. No outbox/inbox/checkpoint rows changed. N4/N5/N6 were not entered. No worker was started.
