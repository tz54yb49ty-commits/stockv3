# N3 20260612 B2 Fact-Only Projection Time Policy Midday Repair

## Result

- result: `IMPLEMENTATION_PASS`
- layer_role: `N3_market_data`
- policy: `fact_only_defer_off_bucket_source_snapshot_time`
- handling: `NOOP_PASS_NO_WRITE`

## Root Cause

Dynamic B2 fact-only contracts omitted `projection_time_policy`. The B2 runner therefore defaulted to `source_snapshot_time`; observed/source snapshot times such as `12:05` fell outside reviewed trading buckets and BLOCKED inside `projection_window_for_snapshot`.

## Policy Decision

Use midday/off-bucket defer/NOOP. The runner does not map `12:05` to a trading bucket and does not forge closed data. If any source snapshot row is outside trading buckets, B2 returns `NOOP_PASS` before projection row build and before any DB write.

## Implementation Proof

- Generator now emits `projection_time_policy` in B2 dry-run, execute contract, and execute preflight.
- Runner checks off-bucket source snapshot times after source-lineage checks and before `build_projection_rows` / `write_projection_execute_transaction`.
- NOOP report has `writes_performed=false`, `projection_fact_written=false`, `quality_item_written=false`, and `event_outbox_written=false`.
- Existing 20260612 B2 artifacts were refreshed so later generator passes do not conflict with stale `projection_time_policy=null` files.

## Validation

- RED observed: missing artifact policy and missing runner no-op detector.
- Targeted tests: `38 OK`.
- Compileall: `PASS`.
- JSON parse: `84` 20260612 B2 JSON artifacts parsed.
- Artifact policy check: all checked artifacts include `fact_only_defer_off_bucket_source_snapshot_time`.
- Forbidden scope scan: `PASS`.
- `git diff --check`: `PASS`.

## Forbidden Scope

No scheduler or wrapper was started, no B1/C1/B2/N4/N5/N6 execute was run, no database write or rollback execution occurred, and no outbox/inbox/checkpoint, voice/mobile/sim/trade, or old-system path was touched.

## Next Prompt

`layer_role=runtime_control。进入 N3_20260612_B2_FACT_ONLY_PROJECTION_TIME_POLICY_MIDDAY_REPAIR_POST_REVIEW_GATE。`
