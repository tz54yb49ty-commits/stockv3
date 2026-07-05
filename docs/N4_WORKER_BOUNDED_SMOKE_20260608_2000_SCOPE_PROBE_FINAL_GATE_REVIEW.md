# N4 Worker Bounded Smoke 2000 Scope Final Gate Review

Result: `PASS`

## Gate Proof

```text
dry-run=DRY_RUN_PASS
contract=CONTRACT_PASS
preflight=PREFLIGHT_PASS
P0/P1/P2=0/1/0
```

P1 is advisory: this is a consumption-only bounded smoke and not long-running worker approval.

## Source / Baseline Proof

```text
N3 MarketSnapshotUpdated pending=2155
selected source events=2000
selected pending=2000/2000
delivered/delivering=0/0
event_id/dedup_key/partition_key/schema/payload=2000/2000
payload trace fields=2000/2000
target baseline run/quality/state/match/outbox/inbox/checkpoint=0/0/0/0/0/0/0
downstream refs=0
```

## Planned Write Scope

```text
common_trigger_run=1
common_trigger_quality_item=2
common_event_inbox=2000
common_event_consumer_checkpoint=2000
common_trigger_state=0
common_trigger_match=0
common_event_outbox=0
N3 outbox status update=0
N5/N6 refs=0
```

## Boundary

```text
semantic_smoke=false
fixture_only=false
not_new_market_decision=true
TriggerMatched=0
TriggerPendingMarketData=0
TriggerStateChanged=0
N5 entry=0
long_running_worker_allowed=false
```

## Allowed Execute Command

```bash
PYTHONPATH=src:scripts python3 scripts/run_n4_worker_bounded_smoke_once.py \
  --contract-path docs/N4_WORKER_BOUNDED_SMOKE_20260608_2000_SCOPE_PROBE_CONTRACT.json \
  --smoke-run-id n4_worker_bounded_smoke_20260608_2000_scope_probe \
  --consumer-name n4_trigger_worker_v1_bounded_smoke_2000_scope_probe \
  --source-run-id realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute \
  --source-event-type MarketSnapshotUpdated \
  --source-trade-date 20260608 \
  --max-events 2000 \
  --max-runtime-seconds 900 \
  --heartbeat-interval-seconds 10 \
  --stop-file tmp/n4_worker_bounded_smoke_20260608_2000_scope_probe.stop \
  --status-json docs/N4_WORKER_BOUNDED_SMOKE_20260608_2000_SCOPE_PROBE_STATUS.json \
  --json-report-path docs/N4_WORKER_BOUNDED_SMOKE_20260608_2000_SCOPE_PROBE_EXECUTE_REPORT.json \
  --markdown-report-path docs/N4_WORKER_BOUNDED_SMOKE_20260608_2000_SCOPE_PROBE_EXECUTE_REPORT.md \
  --rollback-sql-path sql/N4_worker_bounded_smoke_20260608_2000_scope_probe_rollback.sql \
  --execute \
  --user-confirmed
```

This command is allowed only for the next user-confirmation gate. It was not executed in this gate.

