# N1 20260605 Close And 20260608 Calendar Repair Dry-Run

result: `DRY_RUN_PASS_WITH_REPAIR_REQUIRED`

This is a runtime_control dry-run. It did not execute N1 writes.

## Current State

Calendar:

```text
20260605 exists, is_open=true, prev=20260604, next=20260608
20260608 missing
```

N1 20260605 source rows:

| Table | Rows |
|---|---:|
| stock_daily_bar_fact | 0 |
| index_daily_bar_fact | 0 |
| board_daily_bar_fact | 0 |
| stock_daily_basic | 0 |
| stock_financial_metrics_fact | 0 |
| index_membership_fact | 0 |
| board_membership_fact | 0 |

Target batch conflicts:

| Batch | Conflicts |
|---|---:|
| trade_calendar_20260608_patch_v1 | 0 |
| official_daily_ingest_20260605_v1 | 0 |
| condition_source_activation_20260605_v1 | 0 |

Downstream refs:

```text
N2 refs=0
N3 refs=0
N4 refs=0
N5 broad refs=0
```

## Planned Repairs

1. Patch `common_trade_calendar` for `20260608`.
2. Ingest 20260605 stock/index/board daily close facts.
3. Activate 20260605 condition source rows for daily basic, financial, and membership facts.

All three steps require separate N1 final gates and explicit user confirmation.

## P0/P1/P2

```text
P0=0
P1=2
P2=1
```

P1 items:

- generic daily incremental runner requires N1 final gate
- date-specific 20260605 condition-source runner was not confirmed

P2 item:

- the full one-shot objective crosses N1/N2/N3 layer boundaries

## Forbidden Scope

This dry-run did not:

- write database rows
- execute N1/N2/N3
- pull market data
- enter N4/N5/N6
- consume or update outbox/inbox/checkpoint
- start worker
- touch the old system

## Next Gate

```text
N1_20260605_CLOSE_AND_20260608_CALENDAR_REPAIR_EXECUTE_FINAL_GATE_REVIEW
```

