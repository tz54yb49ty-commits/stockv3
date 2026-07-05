# N3 20260617 Full-Day Current Minute Excluding BJ Blocker Scoped C1 Backfill

- result: `BLOCKED`
- blocked_reason: `included_source_coverage_not_exactly_240_through_1500_before_db_write`
- database_written: `false`
- rollback_sql_path: `null`
- allowed_next_prompt: `no B2/N4 handoff`

## Included Scope Row Proof

- stock: `1841` identities, `1840` passed, `1` failed; min/max rows `239/240`, max_hhmm `15:00`
- index: `81` identities, `81` passed, `0` failed; min/max rows `240/240`, max_hhmm `15:00`
- board: `127` identities, `127` passed, `0` failed; min/max rows `240/240`, max_hhmm `15:00`

Blocking included identity:

- `stock:SH:688143`: rows `239`, missing_hhmm `11:30`, max_hhmm `15:00`

## Excluded BJ Blocker Proof

- excluded identities: `index:BJ:899050`, `index:BJ:899601`
- excluded repaired-lineage current minute rows before write: `0`
- excluded minute facts written: `0` because C1 stopped before DB write
- quality-visible blocker rows written: `0` because C1 stopped before DB write

## Target Cleanliness

Post-block DB proof remains clean: planned C1 run rows `0`, quality rows `0`, stock/index/board minute rows `0/0/0`, B2 metric rows `0/0/0`, outbox/inbox/checkpoint refs `0/0/0`.

## Next

No B2/N4 handoff. Rerun N3 source acquisition only after an N3-allowed source can prove every included identity has exactly `240` rows through `15:00`.
