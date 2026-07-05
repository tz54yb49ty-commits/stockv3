# N3-EOD Snapshot Schema Readiness

## Result

SCHEMA_READINESS_PASS

This readiness pass is for N3 EOD snapshot refresh schema only. It is a settlement / official close confirmation extension and does not execute EOD, pull market data, write business rows, write outbox, consume C3 outbox, enter N4/N5/N6, or start a worker.

## Scope

Migration draft:

```text
sql/019_market_eod_snapshot_schema.sql
```

Schema rollback draft:

```text
sql/019_market_eod_snapshot_rollback.sql
```

Business rollback draft:

```text
sql/N3_EOD_snapshot_business_rollback.sql
```

## Additive Tables

The schema draft creates six new N3 EOD physical tables:

```text
stock_eod_snapshot
index_eod_snapshot
board_eod_snapshot

stock_eod_reconciliation_item
index_eod_reconciliation_item
board_eod_reconciliation_item
```

It keeps stock / index / board physically separated. It does not reuse or alter:

```text
stock_realtime_daily_snapshot
index_realtime_daily_snapshot
board_realtime_daily_snapshot
stock_realtime_projection_metric
index_realtime_projection_metric
board_realtime_projection_metric
stock_closed_30m_summary
index_closed_30m_summary
board_closed_30m_summary
stock_closed_30m_signal_enrichment
index_closed_30m_signal_enrichment
board_closed_30m_signal_enrichment
stock_minute_bar_1m
index_minute_bar_1m
board_minute_bar_1m
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
```

## Strictly Additive Check

The 019 schema draft is strictly additive:

```text
CREATE TABLE IF NOT EXISTS: 6
CREATE INDEX IF NOT EXISTS: 48
ALTER old tables: 0
DROP: 0
INSERT / UPDATE / DELETE / TRUNCATE: 0
outbox / inbox / checkpoint writes: 0
N4 / N5 / N6 writes: 0
```

## EOD Contract Summary

EOD is a settlement fact and official close confirmation stage.

It must not:

```text
supersede B1/B2/N4/N5
automatically trigger replay
consume C3 outbox
write MinuteBarClosed
write N4/N5/N6
start a worker
```

The EOD run id is:

```text
eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
```

## Source Allowlist

Future dry-run / execute may only read the explicit lineage allowlist:

```text
B1 realtime_daily_snapshot run
C2 closed_30m_summary run
C2B closed_signal_enrichment run
C3 MinuteBarClosed outbox status
N4 C3 replay audit run
N1 official daily fact run, if available
```

If N1 official daily fact is missing, dry-run must emit:

```text
missing_official_daily_fact
```

and official-confirm execute must be blocked until a separate N1 official daily ingestion gate is approved and passed.

## Future Execute Scope

Allowed future execute writes:

```text
common_market_data_run
common_market_data_quality_item
stock_eod_snapshot
index_eod_snapshot
board_eod_snapshot
stock_eod_reconciliation_item
index_eod_reconciliation_item
board_eod_reconciliation_item
```

Forbidden future execute writes:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
common_event_delivery_attempt
realtime_projection_metric
realtime_daily_snapshot
closed_30m_summary
closed_30m_signal_enrichment
minute_bar_1m
C3 outbox
N4/N5/N6
worker
old system
```

## Rollback

Schema rollback:

```text
sql/019_market_eod_snapshot_rollback.sql
```

Schema rollback may drop the six EOD tables only if all six have row_count=0.

Business rollback:

```text
sql/N3_EOD_snapshot_business_rollback.sql
```

Business rollback deletes only rows scoped by `eod_run_id` from:

```text
stock/index/board_eod_reconciliation_item
stock/index/board_eod_snapshot
common_market_data_quality_item
common_market_data_run
```

It must block if any EOD-scoped outbox, inbox, or checkpoint reference exists.

## Decision

```text
019 migration review allowed: yes
019 migration execute allowed now: no, requires explicit user confirmation
EOD business dry-run implementation allowed after 019 review/execute: yes
EOD business execute allowed now: no
```
