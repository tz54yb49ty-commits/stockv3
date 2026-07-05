# N3 Market Data Historical Replay Pull Policy Contract

Status: CONTRACT_PASS

Generated at: 2026-06-07T16:19:27+08:00

## Scope

This runtime_control gate defines a historical/replay pull policy for:

```text
subscription_run_id=market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
source_condition_run_id=condition_layer_20260528_source_20260528_v6
source_trade_date=20260528
for_trade_date=20260529
prev_trade_date=20260528
current_date=20260607
```

This gate does not pull market data, does not write DB facts/status rows, does not write outbox events, does not consume/update outbox/inbox/checkpoint, does not start workers, does not enter N4/N5/N6, does not execute rollback SQL, and does not touch the old system.

## Context

The ordinary pull readiness gate was blocked because `current_date != for_trade_date`. N3 rules keep ordinary `realtime_daily_snapshot` as a live intraday snapshot:

```text
ordinary realtime_daily_snapshot execute requires current_date == for_trade_date
current_date=20260607
for_trade_date=20260529
```

The subscription itself is clean:

```text
subscription status=passed
P0/P1/P2=0/0/0
pull_plan rows=9
pull_plan.execute_allowed=false: 9/9
facts/projection/outbox/downstream refs=0
```

## Policy Decision Matrix

| required_data_kind | Objects | Policy When current_date != for_trade_date | Decision |
|---|---:|---|---|
| realtime_daily_snapshot | 2522 | ordinary realtime blocked; historical snapshot requires a separate adapter contract | SPLIT_TO_SEPARATE_GATE |
| minute_bar_1m | 256 | historical replay allowed only with explicit replay mode and closed-minute cutoff | REQUIRE_EXPLICIT_REPLAY_MODE |
| previous_day_minute_bar_1m | 256 | historical preload allowed with preload status and quality rows | ALLOW_HISTORICAL_REPLAY |

## Recommended Path

Recommended option: A. Split gate.

```text
previous_day_minute_bar_1m -> historical preload contract
minute_bar_1m -> historical closed-minute replay contract with cutoff
realtime_daily_snapshot -> remains blocked unless a historical snapshot adapter contract is introduced
```

Rationale:

- Preserves the N3 hard rule for ordinary realtime snapshots.
- Gives previous-day preload and historical minute replay separate rollback boundaries.
- Avoids live `MarketSnapshotUpdated` outbox for historical/replay data.
- Avoids a broad unified replay command that would mix live snapshot, historical minute, and preload semantics.

## Rejected Paths

Option B, unified replay gate, is rejected for now because it would require new adapter and event semantics for all three data kinds, including historical snapshot timestamp policy.

Option C, block all, is not recommended because the subscription is clean and minute data can proceed through audited historical gates.

## Freshness And Date Policy

```text
ordinary realtime_daily_snapshot execute requires current_date == for_trade_date
ordinary realtime_daily_snapshot current-date mismatch remains P0 for ordinary execute
historical snapshot requires a new adapter contract
historical snapshot must define source_adapter and data timestamp policy
historical snapshot must not write live MarketSnapshotUpdated outbox by default
today minute historical replay requires closed-minute cutoff
today minute historical replay must not use unclosed minutes
previous-day minute preload must preserve preload status and quality
```

## Outbox/Event Policy

Historical/replay pull defaults to no live outbox.

If replay events are later required, they must be explicitly marked as replay, include source_run_id lineage, and pass a separate event policy gate.

## Rollback Requirements

Future pull rollback must:

```text
hard-fail before DELETE/UPDATE
delete only scoped replay-written fact/status/quality/run rows
not delete subscription control rows
block if projection/outbox/N4/N5/N6 refs exist
contain no CASCADE/DROP/TRUNCATE
```

## Required Follow-Up Gates

```text
N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_CONTRACT_GATE_FOR_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
N3_TODAY_MINUTE_HISTORICAL_CLOSED_MINUTE_REPLAY_CONTRACT_GATE_FOR_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
```

Optional future gates:

```text
N3_HISTORICAL_DAILY_SNAPSHOT_ADAPTER_CONTRACT_GATE_FOR_20260529
N3_REPLAY_EVENT_OUTBOX_POLICY_CONTRACT_GATE
```

## Forbidden Scope Proof

```text
database_written=false
pull_executed=false
market_data_pulled=false
realtime_daily_snapshot_written=false
minute_bar_1m_written=false
previous_day_preload_status_written=false
outbox_written_or_consumed=false
inbox_or_checkpoint_updated=false
worker_started=false
entered_n4_n5_n6=false
rollback_sql_executed=false
old_system_touched=false
```

## P0/P1/P2

```text
P0=0
P1=2
P2=0
```

P1 notes:

- Ordinary realtime snapshot is blocked by date policy, accepted here as a policy boundary.
- Today minute replay still requires a closed-minute cutoff contract.

## Next Gate

```text
N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_CONTRACT_GATE_FOR_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
```
