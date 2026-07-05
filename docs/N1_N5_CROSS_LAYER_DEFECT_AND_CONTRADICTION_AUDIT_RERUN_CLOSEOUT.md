# N1-N5 Cross-Layer Defect and Contradiction Audit Rerun Closeout

Gate: `N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT_RERUN_CLOSEOUT_GATE`

Result: `CLOSEOUT_PASS`

Layer role: `runtime_control`

Source gate: `N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT_RERUN_GATE = AUDIT_RERUN_PASS`

This closeout only registers the rerun result and writes closeout artifacts. It does not modify code, write the database, execute N1-N5 commands, roll back, consume or update outbox, start a worker, enter N6 implementation, generate proposal/order/trade, update position/PnL, or touch real trade.

## Closed Finding Summary

| finding | severity | closeout status | proof |
|---|---:|---|---|
| `N1N5-P0-001` | P0 | `CLOSED` | N5 execute report top-level quality and embedded dry-run quality are both `0/0/0`; baseline/current read event count is `605/605`. |
| `N1N5-P0-002` | P0 | `CLOSED` | N4/N5 downstream ref registration repair is complete; current proof now uses fresh rerun DB evidence. |
| `N1N5-P1-001` | P1 | `CLOSED_FUTURE_WRITE_ONLY` | N4 `dual_proof` policy fixes future writes. Existing 605 fact rows are registered as historical-only, not silently backfilled. |
| `N1N5-P1-002` | P1 | `CLOSED` | N5 checkpoint semantics are split: accepted/inbox/plan event count `605`; physical checkpoint watermark rows `73`. |
| `N1N5-P1-003` | P1 | `CLOSED` | Old 1537-row blocked N5 dry-run is superseded and retained as historical evidence only. |
| `N1N5-P2-001` | P2 | `CLOSED` | `AGENTS.md` is now a status stub and no longer owns stale concrete live lineage or row/outbox counts. |
| `N1N5-P2-002` | P2 | `CLOSED` | Legacy projection matcher route is fenced and not allowed as current 20260605 v4 corrected route. |

## Active Remaining

```text
active P0/P1/P2 = 0/0/0
active blockers = 0
```

## Historical-Only Blocker Registry

```text
finding_id=N1N5-P1-001
status=HISTORICAL_BLOCKER_REGISTERED
affected_table=common_trigger_match
affected_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
affected_rows=605
condition=existing raw_json rows do not have top-level mirrors of v4 required fields
canonical cross-layer proof=common_event_outbox.payload_json required fields complete 605/605
future-write status=fixed by dual_proof policy
not done in this gate=no historical row backfill
optional repair gate=N4_V4_TRIGGER_MATCH_FACT_RAW_JSON_HISTORICAL_REPAIR_CONTRACT_GATE
```

## Fresh DB Proof Registry

Source: `docs/N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT_RERUN.json`

Target DB:

```text
database=ashare_v3
user=ashare_v3_user
host=127.0.0.1/32
port=5432
db_time=2026-06-08T23:06:53.704615+08:00
```

N4:

```text
trigger_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
status=passed
P0/P1/P2=0/1/0
common_trigger_state=605
common_trigger_match=605
common_trigger_quality_item=4
common_event_outbox TriggerMatched pending=605
outbox payload required fields complete=605/605
trigger_match.raw_json required fields complete=0/605 historical rows not rewritten
```

N5:

```text
action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
status=passed
P0/P1/P2=0/0/0
common_action_event=605
common_event_inbox processed=605
common_event_consumer_checkpoint scoped rows=73
N5 outbox ActionBlocked pending=604
N5 outbox ActionExecuted pending=1
```

## Downstream N6 Refs Note

N6 is not audited for functional completion in this closeout. The following refs are registered only so future rollback/readiness gates do not assume downstream refs are zero:

```text
user_projection_run=1
user_signal_projection=605
user_signal_card=605
user_notification_queue=0
n6_virtual_order/trade/position/position_event/pnl=0/0/0/0/0
total refs=1211
```

These refs do not reopen the original N1-N5 findings, but they must be considered before any future rollback or downstream readiness gate.

## Forbidden Scope Proof

```text
code_modified=false
database_written=false
execute_performed=false
rollback_performed=false
outbox_consumed_or_updated=false
worker_started=false
n6_implementation_entered=false
proposal_order_trade_touched=false
position_pnl_touched=false
real_trade_touched=false
```

## Next Recommended Gate

Primary:

```text
N1_N5_REMEDIATION_PROGRAM_FINAL_REGISTRATION_GATE
```

Optional only if runtime_control wants historical live fact-row backfill:

```text
N4_V4_TRIGGER_MATCH_FACT_RAW_JSON_HISTORICAL_REPAIR_CONTRACT_GATE
```

## Validation

```text
source rerun result=PASS
JSON parse=PASS
evidence grep=PASS
git diff --check=PASS
```
