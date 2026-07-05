# N3/N4/N5 Structured Query Audit Artifact Filename Hardening Report

Gate: `N3_N4_N5_STRUCTURED_QUERY_AUDIT_ARTIFACT_FILENAME_HARDENING_GATE`

Result: `HARDENING_PASS`

Layer role: `runtime_control`

Generated at: `2026-06-07T04:46:33.318543+00:00`

## Root Cause

`make_artifact_audit_sink()` previously used the full `audit_run_id` directly as the local JSON filename. N4 projection matcher lineage can be longer than filesystem filename limits, while the full lineage still needs to be preserved inside the audit JSON.

## Implementation Summary

- Changed `src/ashare_v3/observability/query_audit.py`.
- Added `MAX_AUDIT_ARTIFACT_FILENAME_BYTES=180`.
- New filenames use a bounded safe prefix plus deterministic 16-hex digest suffix.
- Full `audit_run_id` remains unchanged in the JSON report.
- Added regression test in `tests/test_structured_query_audit.py`.

## Red/Green Proof

- RED: the new regression test failed with `OSError [Errno 63] File name too long` before implementation.
- GREEN: the same test passed after hardening.

## N4 Probe Proof

- N4 read-only dry-run result: `DRY_RUN_PASS`
- compliant_count: `605`
- blocked_count: `291`
- execute_preflight_could_pass: `True`
- new audit filename bytes: `179`
- full audit_run_id bytes preserved in JSON: `281`
- audit summary: `{"total_entries": 3, "blocked_entries": 0, "denied_table_hit_entries": 0, "db_write_attempted_entries": 0, "worker_started_entries": 0, "outbox_consumed_entries": 0, "checkpoint_updated_entries": 0}`

## P0/P1/P2

`P0/P1/P2 = 0/1/0`

P1: audited fresh-run validation still needs recontract for current post-closeout N3/N5 probes. This hardening gate only resolves the N4 filename blocker.

## Forbidden Scope Proof

No database write, migration, rollback, outbox/inbox/checkpoint consumption or update, worker startup, delivery/push/voice/mobile, sim/position/PnL/real_trade, proposal/order/trade, PostgreSQL config change, or pg_stat_statements enablement was performed.

## Next Gate Recommendation

`N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_RECONTRACT_GATE`

## Validation Summary

- JSON parse: `PASS`
- structured query audit/adoption unittests: `23 OK`
- `python3 -m compileall src/ashare_v3/observability src/ashare_v3/trigger src/ashare_v3/action`: `PASS`
- `git diff --check`: `PASS`
