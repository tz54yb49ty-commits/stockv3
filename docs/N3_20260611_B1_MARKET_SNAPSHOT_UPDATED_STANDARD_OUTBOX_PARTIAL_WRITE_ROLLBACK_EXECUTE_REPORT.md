# N3 20260611 B1 MarketSnapshotUpdated Standard Outbox Partial Write Rollback Execute Report

## Result

ROLLBACK_PASS

## Scope

Layer role: N3_market_data.

This gate executed only the scoped rollback for:

```text
realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1
```

It did not consume or update outbox/inbox/checkpoint, did not start workers, did not enter N4/N5/N6, and did not touch delivery, push, voice, mobile, proposal, order, trade, sim, position, PnL, real trade, or the old system.

## Execution

The registry rollback SQL remains default hard-fail protected:

```text
sql/N3_20260611_B1_market_snapshot_updated_standard_outbox_rollback.sql
```

For this user-confirmed execute gate, an authorized temporary execution copy was created at:

```text
/tmp/N3_20260611_B1_market_snapshot_updated_standard_outbox_rollback_authorized_execute.sql
```

Only the default hard-fail block was removed from the temporary copy. Scoped guards and delete scope were preserved.

Executed command:

```bash
/opt/homebrew/Cellar/postgresql@16/16.14/bin/psql "$DEFAULT_DSN" -v ON_ERROR_STOP=1 \
  -f /tmp/N3_20260611_B1_market_snapshot_updated_standard_outbox_rollback_authorized_execute.sql
```

Target DB proof:

```text
db=ashare_v3
user=ashare_v3_user
host=127.0.0.1
port=5432
```

## Deleted Rows

psql output:

| target | deleted rows |
|---|---:|
| `common_event_outbox` | 1973 |
| `stock_realtime_daily_snapshot` | 1890 |
| `index_realtime_daily_snapshot` | 83 |
| `board_realtime_daily_snapshot` | 0 |
| `common_market_data_quality_item` | 138 |
| `common_market_data_run` | 1 |

Transaction result: `COMMIT`.

## Post-Rollback Baseline

| target | rows |
|---|---:|
| `stock_realtime_daily_snapshot` | 0 |
| `index_realtime_daily_snapshot` | 0 |
| `board_realtime_daily_snapshot` | 0 |
| `common_market_data_quality_item` | 0 |
| `common_market_data_run` | 0 |
| scoped `common_event_outbox` | 0 |

Global 20260611 `MarketSnapshotUpdated`:

| status | rows |
|---|---:|
| total | 0 |
| pending | 0 |

## Boundary Proof

- scoped inbox refs: `0`
- scoped checkpoint refs: `0`
- N3-B2/N4/N5/N6/user/sim/virtual downstream refs total: `0`
- rollback SQL executed: yes, scoped only
- outbox consumed or updated: no
- worker started: false
- N4/N5/N6 entered: false

Existing fact-only B1/C1/B2 runs were not targeted. Read-only sample shows non-target 20260611 intraday runs still present with `status=passed`, `downstream_layers_touched=false`, and `worker_started=false`.

## Rollback Safety

The original registry SQL still contains the default hard-fail and remains safe for future review.

Next gate:

```text
N3_B1_STANDARD_OUTBOX_RUN_LEVEL_ATOMIC_SOURCE_TIME_GUARD_IMPLEMENTATION_GATE
```
