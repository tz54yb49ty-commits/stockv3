# N1-N5 Cross-Layer Defect and Contradiction Audit Rerun

Gate: `N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT_RERUN_GATE`

Result: `AUDIT_RERUN_PASS`

Layer role: `runtime_control`

This rerun is read-only for the live database and business layers. It does not execute N1-N5 commands, does not roll back, does not consume or update outbox, does not start workers, and does not enter N6 implementation, proposal/order/trade, position/PnL, or real trade.

## Finding Closure Summary

| finding | severity | rerun status | summary |
|---|---:|---|---|
| `N1N5-P0-001` | P0 | `CLOSED` | N5 execute report no longer has `EXECUTED` plus nested P0 failed contradiction. Baseline is `N5_action_pipeline_execute_contract`, `605 -> 605`, delta `0`, explainable `true`. |
| `N1N5-P0-002` | P0 | `CLOSED` | N4/N5 downstream ref registration repaired by `N4_N5_DOWNSTREAM_REF_REGISTRATION_REPAIR`. Fresh DB proof is used for current refs. |
| `N1N5-P1-001` | P1 | `CLOSED_FUTURE_WRITE_ONLY` | N4 policy is `dual_proof`; future writes mirror v4 required fields into `common_trigger_match.raw_json`. Existing 605 rows are not rewritten and are registered as historical-only. |
| `N1N5-P1-002` | P1 | `CLOSED` | N5 checkpoint semantics are split: accepted/inbox/plan events `605`; physical checkpoint watermark rows `73`. |
| `N1N5-P1-003` | P1 | `CLOSED` | Old 1537-row blocked dry-run is superseded and preserved as historical evidence only. |
| `N1N5-P2-001` | P2 | `CLOSED` | `AGENTS.md` no longer owns stale concrete live lineage; it points to authority docs and fresh gate artifacts. |
| `N1N5-P2-002` | P2 | `CLOSED` | Legacy `projection_matcher_execute` has deprecation metadata and a selection fence blocking the current 20260605 v4 corrected run. |

Active remaining findings:

```text
P0/P1/P2 = 0/0/0
```

Historical-only blockers:

```text
N1N5-P1-001: existing 605 common_trigger_match.raw_json rows were not backfilled.
```

## Fresh DB Proof

Target DB:

```text
database=ashare_v3
user=ashare_v3_user
host=127.0.0.1/32
port=5432
db_time=2026-06-08T23:06:53.704615+08:00
```

N4 corrected trigger run:

```text
run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
status=passed
P0/P1/P2=0/1/0
P1 note=n4_v4_corrected_blocked_candidates_visible warning=291, non-blocking quality visibility
common_trigger_state=605
common_trigger_match=605
common_trigger_quality_item=4
common_event_outbox TriggerMatched pending=605
signal_type B_BUY=573 S_SELL=32
outbox payload v4 required fields complete=605/605
common_trigger_match.raw_json v4 required fields complete=0/605 historical rows not rewritten
```

N5 action run:

```text
run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
status=passed
P0/P1/P2=0/0/0
trigger_outbox_row_count=605
action_candidate_row_count=605
action_fact_row_count=605
common_action_event=605
common_event_inbox processed=605
common_event_consumer_checkpoint scoped rows=73
common_event_outbox ActionBlocked pending=604
common_event_outbox ActionExecuted pending=1
```

N6 downstream refs proof, not N6 functional audit:

```text
user_projection_run refs=1
user_signal_projection refs=605
user_signal_card refs=605
user_notification_queue refs=0
n6_virtual_order/trade/position/position_event/pnl refs=0/0/0/0/0
total registered N6 downstream refs=1211
```

This means future rollback/readiness gates must account for N6 user projection refs. It does not reopen the original N1-N5 findings.

## Artifact Proof

N5 artifact reconciliation:

```text
N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_REPORT result=RECONCILED
N5 execute report result=EXECUTED
top-level quality P0/P1/P2=0/0/0
dry_run_plan quality P0/P1/P2=0/0/0
baseline_kind=N5_action_pipeline_execute_contract
baseline_read_event_count=605
current_read_event_count=605
read_event_count_delta=0
explainable=true
checkpoint_physical_watermark_rows=73
live_checkpoint_ref_rows=73
```

N4 dual proof:

```text
recommended_policy=dual_proof
future_write_fixed=true
historical_live_rows_rewritten=false
next historical repair gate=N4_V4_TRIGGER_MATCH_FACT_RAW_JSON_HISTORICAL_REPAIR_CONTRACT_GATE
```

N4 legacy route fence:

```text
LEGACY_PROJECTION_MATCHER_ROUTE_METADATA present
assert_legacy_projection_route_allowed present
current run id blocked=true
allowed_for_current_v4_corrected_flow=false
allowed_for_20260605_n4_execute_gate=false
n5_entry_source_for_current_chain=false
uses_old_outbox_consuming_projection_matcher_execute_route=false in current N4 contract/preflight
```

## Residual Notes

- `N1N5-P1-001` is closed for future writes, but the existing 605 `common_trigger_match.raw_json` rows are historical-only until an explicit historical repair gate is approved.
- N6 user projection refs now exist for the N5 action run. This is current downstream proof and must be considered by any future rollback gate.
- `docs/N5_ACTION_PIPELINE_EXECUTE_REPORT.json` still contains a legacy `inserted_counts.common_event_consumer_checkpoint=605` field. The authoritative reconciliation fields now distinguish `accepted_event_count=605` from `checkpoint_physical_watermark_rows=73`, and planned/expected row counts use `73`.

## Recommended Next Gate

Primary:

```text
N1_N5_CROSS_LAYER_DEFECT_AND_CONTRADICTION_AUDIT_RERUN_CLOSEOUT_GATE
```

Optional, only if runtime_control wants live fact-row backfill for historical proof:

```text
N4_V4_TRIGGER_MATCH_FACT_RAW_JSON_HISTORICAL_REPAIR_CONTRACT_GATE
```

## Validation

```text
JSON parse=PASS
evidence grep=PASS
readonly DB proof=PASS
git diff --check=PASS
```
