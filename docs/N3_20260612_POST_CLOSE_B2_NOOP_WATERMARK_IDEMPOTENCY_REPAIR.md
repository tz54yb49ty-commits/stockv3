# N3 20260612 Post-Close B2 NOOP Watermark Idempotency Repair

Result: `REPAIR_PASS`

## Root Cause

The auto chain successfully completed `15:00`, but the next post-close interval blocked before executing any child:

```text
chain blocked_reason=n3_auto_poll_failed
N3 reason=child_artifact_generation_failed
executed_child_command_count=0
```

The direct cause was a valid B2 fact-only no-write result:

```text
docs/N3_B2_realtime_projection_20260612_until_1500_execute_report.json
result=NOOP_PASS
noop_reason=off_bucket_source_snapshot_time
writes_performed=false
```

Because the B2 NOOP writes no `common_market_data_run` row, the next interval did not see the B2 watermark in DB `passed_run_ids`. It then tried to regenerate the existing `1500` artifacts and rollback SQL, which correctly conflicted.

## Repair

Updated `scripts/run_n3_intraday_b1_c1_b2_auto_poll_once.py`:

- If the only pending child step is B2,
- and its existing execute report is `NOOP_PASS`,
- and `projection_run_id` matches the child run id,
- and `writes_performed=false`,
- then the wrapper returns:

```text
status=noop
reason=latest_closed_minute_b2_noop_already_processed
executed_child_command_count=0
artifact_generation=not_written
```

This treats reviewed no-write B2 NOOP as a processed watermark and prevents repeated post-close artifact conflicts.

## Validation

```text
red/green regression test: PASS
targeted tests: 118 OK
compileall scripts src tests: PASS
scheduler state during repair: not_loaded
```

Forbidden scope held: no scheduler start, no manual wrapper/N3/N4/N5 execute, no DB write by repair, no rollback, no outbox/inbox/checkpoint mutation, no N6/voice/mobile/sim/trade.

Next:

```text
N3_N4_N5_20260612_REALTIME_AUTO_CHAIN_POST_CLOSE_NOOP_REACTIVATION_OBSERVATION
```
