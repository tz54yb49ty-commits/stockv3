# N1 20260605 Close And 20260608 Calendar Repair Execute Final Gate Review

review_result: `BLOCKED_FOR_FULL_REPAIR`

layer_role: `runtime_control`

## Summary

The full N1 repair sequence cannot be released as a single execute yet.

The 20260608 calendar patch is ready for a separate `N1_ingestion` user confirmation gate. The 20260605 official daily ingestion and condition-source activation are blocked until a guarded 20260605 runner/contract/preflight exists.

## Calendar Patch Finding

`docs/N1_trade_calendar_20260608_patch_preflight.json` returned:

```text
result=PREFLIGHT_PASS
P0/P1/P2=0/0/0
tushare_available=true
trade_date=20260608
is_open=true
prev_trade_date=20260605
next_trade_date=20260609
target_calendar_rows=0
target_active_rows=0
patch_batch_conflict=0
```

Allowed calendar patch command, only after switching to `layer_role=N1_ingestion` and explicit user confirmation:

```bash
PYTHONPATH=src:scripts python3 scripts/run_trade_calendar_patch_once.py \
  --dsn postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3 \
  --trade-date 20260608 \
  --expected-prev-trade-date 20260605 \
  --fallback-next-trade-date 20260609 \
  --source-batch-id trade_calendar_20260608_patch_v1 \
  --source-version trade_calendar_20260608_patch_v1 \
  --json-report-path docs/N1_trade_calendar_20260608_patch_preflight.json \
  --markdown-report-path docs/N1_TRADE_CALENDAR_20260608_PATCH_PREFLIGHT.md \
  --rollback-sql-path sql/N1_trade_calendar_20260608_patch_rollback.sql \
  --execute --user-confirmed --postgres-commit-enabled
```

## Blocked Findings

Official daily 20260605 ingestion:

```text
result=BLOCKED
reason=no date-specific 20260605 official daily runner/contract artifact found
additional_reason=scripts/run_real_daily_incremental.py has no --execute/--user-confirmed guard flags
```

Condition source 20260605 activation:

```text
result=BLOCKED
reason=no date-specific 20260605 condition-source runner/contract artifact found
dependency=official daily 20260605 ingestion must pass first
```

N2/N3:

```text
result=BLOCKED
reason=N1 20260605 source facts and condition source are not active yet
```

## Approved Scope

Only the following scope is approved for the next user confirmation point:

```text
N1 calendar patch for 20260608 only
```

## Blocked Scope

The following remain blocked:

- N1 official daily 20260605 ingestion execute
- N1 condition source 20260605 activation execute
- N2 condition layer for `source_trade_date=20260605`, `for_trade_date=20260608`
- N3 subscription rebuild for 20260608
- N3-A1 previous-day minute preload for 20260605
- N4/N5/N6

## Rollback Proof

| Scope | SQL | Proof |
|---|---|---|
| calendar patch | `sql/N1_trade_calendar_20260608_patch_rollback.sql` | hard-fail before DELETE/UPDATE; no CASCADE/DROP/TRUNCATE |
| official daily | `sql/N1_official_daily_20260605_ingestion_rollback.sql` | hard-fail before DELETE/UPDATE; no CASCADE/DROP/TRUNCATE |
| condition source | `sql/N1_condition_source_20260605_activation_rollback.sql` | hard-fail before DELETE/UPDATE; no CASCADE/DROP/TRUNCATE |

## Forbidden Scope Proof

This review did not:

- execute a runtime command
- write database rows
- execute rollback SQL
- write N1 daily facts
- enter N2/N3/N4/N5/N6
- pull market data
- consume/update outbox/inbox/checkpoint
- start worker
- touch the old system
- enter delivery/push/voice/mobile/sim/position/PnL/real trade
- generate proposal/order/trade

## Next Gate

Immediate allowed next gate:

```text
N1_TRADE_CALENDAR_20260608_PATCH_EXECUTE_USER_CONFIRMATION_GATE
```

Then required:

```text
N1_OFFICIAL_DAILY_20260605_GUARDED_RUNNER_CONTRACT_GATE
```

