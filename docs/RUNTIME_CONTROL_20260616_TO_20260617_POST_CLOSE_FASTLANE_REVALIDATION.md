# Runtime Control 20260616 -> 20260617 Post-Close Fast Lane Revalidation

Result: `REVALIDATION_PASS`

This gate is read-only. It did not execute N1/N2/N3, did not write the database, did not consume or update outbox/inbox/checkpoint, did not enter N4/N5/N6, and did not start workers.

## Current One-Shot Proof

- Status: `EXECUTE_PASS`
- Source trade date: `20260616`
- For trade date: `20260617`
- Status updated at: `2026-06-16T22:26:32.739680+08:00`
- Failed step: `None`

All one-shot substeps passed:

```text
n1_source_facts=PASS
n1_stock_financial_canonical_source_bundle=PASS
n1_stock_financial_canonical_metrics=PASS
n2_condition=PASS
n3_subscription=PASS
n3_a0_preload_dry_run=PASS
n3_a1_contract=PASS
n3_a1_preload=PASS
```

N1 proof:

```text
official_daily rows total=6019
condition_source rows total=80821
stock_financial canonical source=stock_financial_20260616_v2
stock_financial canonical rows=5509
```

N2 proof:

```text
condition_run_id=condition_layer_20260616_source_20260616_for_20260617_v1
stock_condition_basis=5509
index_condition_basis=83
board_condition_basis=427
stock_condition_pool=3902
index_condition_pool=173
board_condition_pool=271
stock_minute_target_scope=3882
index_minute_target_scope=173
board_minute_target_scope=271
```

N3 proof:

```text
subscription candidate/subscription/pull_plan=4774/2499/9
subscription market facts written=0
subscription outbox written=0
A1 objects_processed=224
A1 minute_rows_written=53760
A1 preload_status_rows_written=224
A1 outbox written=0
```

## N1/N2 Modification Impact Assessment

The relevant status timestamp is `2026-06-16T22:26:32+08:00`.

N1/N2 core changes that affect normal one-shot computation were already present before this timestamp and therefore were included in the completed one-shot:

```text
src/ashare_v3/condition/basis.py
src/ashare_v3/ingestion/stock_financial_canonical_metrics.py
src/ashare_v3/ingestion/stock_financial_canonical_source_bundle.py
```

Post-one-shot N1/N2 changes found in the worktree are classified as non-impacting for `20260616 -> 20260617`:

```text
src/ashare_v3/ingestion/stock_financial_002831_tdx_parity_repair.py
scripts/run_stock_financial_002831_tdx_parity_repair_once.py
tests/test_stock_financial_002831_tdx_parity_repair.py
```

Reason: these files implement and test a standalone scoped repair for `source_trade_date=20260615`; they are not invoked by the `20260616 -> 20260617` post-close one-shot.

Docs/UI/status artifacts generated after the one-shot are registration/display work only and do not change N1/N2/N3 computation.

## Decision

```text
rerun_required=false
```

No rerun gate is required for `20260616 -> 20260617`.

## Forbidden Scope Proof

```text
database_written_by_revalidation_gate=false
n1_n2_n3_executed_by_revalidation_gate=false
common_event_outbox_inbox_checkpoint_consumed_or_updated=false
n3_b_c_b2_involved=false
n4_n5_n6_entered=false
worker_started=false
```

Recommended next gate: `NONE`
