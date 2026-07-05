# N3 20260612 B2 Trace-Aligned Standard Outbox Expected Distribution Repair

Result: `REPAIR_PASS`

## Root Cause

The 20260612 chain-generated B2 trace-aligned contract used the newer shape:

```text
expected_projection_rows = { total, by_asset: { stock, index, board } }
```

`realtime_projection_execute.validate_projection_rows_against_contract()` only accepted the legacy flat shape:

```text
expected_projection_rows = { stock, index, board, total }
```

So the runner compared actual `rows_by_asset=1872/83/127` against an empty expected map and blocked before DB writes with:

```text
N3-B2 blocked: projection rows by asset differ from contract
```

## Repair

Updated:

- `src/ashare_v3/market/realtime_projection_execute.py`
- `tests/test_realtime_projection_execute.py`

The validator now accepts both:

- legacy flat `expected_projection_rows.stock/index/board`
- canonical nested `expected_projection_rows.by_asset.stock/index/board`

Zero-count assets are normalized so absent zero rows do not create false mismatches.

## Live Read-Only Proof

Using the existing 1307 contract:

```text
docs/N3_20260612_B2_TRACE_ALIGNED_REALTIME_PROJECTION_METRIC_FOR_STANDARD_OUTBOX_UNTIL_1307_EXECUTE_CONTRACT.json
```

Read-only row-builder validation now passes:

```text
rows=2082
rows_by_asset stock/index/board=1872/83/127
ready/not_ready=297/1785
ready_by_asset stock/index/board=245/33/19
not_ready_by_asset stock/index/board=1627/50/108
validation=PASS
```

No B2 execute runner was called and no DB write was performed.

## Validation

```text
targeted tests: 30 OK
compileall scripts/src/tests: PASS
JSON parse: PASS
forbidden scope scan: PASS
git diff --check: PASS
```

## Forbidden Scope

- Scheduler was not started.
- Wrapper / N3 / N4 / N5 were not manually executed.
- No database write.
- No rollback.
- No outbox/inbox/checkpoint consume or update.
- No N6 / voice / mobile / sim / trade path touched.

Scheduler proof:

```text
com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll: not_loaded
wrapper/N3/N4/N5 process count: 0
```

## Next Gate

```text
layer_role=runtime_control。

进入 N3_20260612_B2_TRACE_ALIGNED_STANDARD_OUTBOX_EXPECTED_DISTRIBUTION_REPAIR_POST_REVIEW_AND_REACTIVATION_FINAL_GATE。

目标：
只读复核 expected_distribution / rows-by-asset compatibility repair 是否可登记为 POST_REVIEW_PASS，并确认是否允许重新 bootstrap com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll。

要求：
不启动 scheduler，不手动执行 wrapper/N3/N4/N5，不写数据库，不执行 rollback，不消费/update outbox/inbox/checkpoint，不进入 N6/voice/mobile/sim/trade。
```
