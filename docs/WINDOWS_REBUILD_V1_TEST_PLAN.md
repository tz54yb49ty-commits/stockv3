# Windows Rebuild v1 Release and Test Plan

## Status

This branch is a code-level release baseline, not a runnable Windows release.
It is built from the Mac authority preservation commit recorded in
`windows-rebuild-manifest.json`.  Database dumping, Windows writes, software
installation, scheduler creation, and N1-N6 runtime execution are outside this
Gate 0.

The immutable tag `windows-rebuild-v1.0.0` must not be created until every W0
condition below passes.

Gate 0 verification on 2026-08-26 compiled 857 Python files and passed the 48
focused archive-governance tests.  Complete legacy `unittest` discovery ran
4612 tests and reported 54 failures, 214 errors, and 19 skips.  Most errors are
tests coupled to date-scoped rollback SQL or historical report fixtures that
the release payload deliberately excludes; additional current-source failures
remain in minute-label semantics and static audit expectations.  These results
are recorded as blockers for the final tag, not hidden or reclassified as a
release pass.

## Release construction checks

1. Verify the source preservation commit and tree against the manifest.
2. Verify that the release payload contains only the manifest allowlist.
3. Verify that Mac untracked reports and rollback SQL remain unmodified and are
   absent from the release index.
4. Verify `git diff --check`, Python compile, the complete unit-test suite, and
   the focused archive-governance tests.
5. Push the release branch and verify its exact remote commit with
   `git ls-remote`.
6. Do not create the final tag while the Windows lock or provider adapters are
   pending.

## Gate W0: native Windows environment

- W0 host mutation is default-deny.  It may run only in a later independent
  `runtime_control` request that exactly satisfies
  `windows_rebuild_w0_bounded_v1`; the policy-definition request must not use
  the exception it defines.
- Verify native CPython 3.11 x64.  Resolve
  `requirements-windows-py311.in` into
  `requirements-windows-py311.lock` with exact versions and hashes only after
  its dependency graph excludes Tushare and Mootdx; otherwise fail closed
  without generating or installing a lock.
- Recreate a fresh venv using only the lock; verify imports for pandas,
  pyarrow, psycopg, FastAPI, Jinja2, Uvicorn, and eltdx.  Verify that importing
  Tushare or Mootdx is unavailable.
- Verify the eltdx installed source is commit
  `b2b94b967f478408848d007c83cc7155367c3aa9`.
- Verify the clean Git checkout commit and the release manifest.
- Install PostgreSQL 16.14 or newer under `D:\PostgreSQL\16`, initialize a new empty
  cluster at `D:\PostgreSQL\16\data`, and bind only to `127.0.0.1`.
  Mac dump, record, source-version, and evidence imports must each remain zero.
  W0 must not create or migrate the `ashare_v3` business schema and must not
  write N1-N6 data.
- Confirm TdxW is logged in, `127.0.0.1:17709` is listening, and method-level
  TQ capability smokes pass.
- Keep every AshareV3 Task Scheduler task disabled.
- Preserve the stopped legacy PostgreSQL 18 program and data unchanged; do not
  uninstall or delete it.  WSL shutdown is a separate native-control phase
  after sealed evidence and `RESTART_REQUIRED`.

## Gate N1

- Start only after an independent W0 PASS.  Build N1 from the empty Windows
  cluster using only TQ, eltdx finance, and a self-built trade calendar.
  Tushare, Mootdx, Mac dumps, Mac records, Mac source versions, and Mac evidence
  are forbidden inputs.
- Freeze non-empty TQ universes for list types 5, 9, 11, 12, and 14.
- Build the three-year daily-bar base from zero in Windows and fill each
  security independently; do not restore an existing base.
- Maintain at least 90 calendar days of expectations; confirm a trading day
  only when valid daily bars cover at least 80% of the frozen list-type-5
  universe.
- Verify boundary cases at 79.99%, 80%, and 100%.
- Complete daily-basic, eltdx finance increment, constituents, and N1 quality
  reports before NAS backup acceptance.

## Gate NAS

- NAS work starts only after Windows N1 acceptance; it is not part of W0.
- Verify DSM share, filesystem, capacity, service account, quota, snapshot or
  versioning capability, and SMB access.
- Complete one base backup, WAL/archive verification, logical dump manifest,
  and an isolated restore drill before enabling N2.
- Never let Codex or the application account delete or change ACLs under the
  PostgreSQL data root on D:.

## Gate N2

- Consume only the new Windows N1 active source.
- Require condition basis, pool, and minute target scope to be
  `passed_active`, with P0 equal to zero and no duplicate business keys.
- Do not fetch external market data from N2.

## Gate N3 A1

- Use the pinned eltdx adapter for the previous trading day's one-minute data.
- Match stock, index, and board subscriptions to N2.
- Require idempotent A1 and cumulative-amount writes with no duplicate minute
  keys.

## Gate N3 B1 to N4 to N5 ActionEligible

Start in this order: N5 ActionEligible intake, N4 consumer, then N3 TQ B1.
Stop in the reverse drain-safe order: stop N3, drain N4, then drain N5.

Acceptance requires at least three continuous natural B1 epochs,
`MarketSnapshotUpdated`, natural canonical N4 events, and idempotent
`ActionEligible` created only from `TriggerMatched`.  Never manufacture a
synthetic business sample.  If no natural match occurs, technical acceptance
may pass while business-sample acceptance remains pending.

## Independent C1/N3T/ActionExecuted lane

- Persist the eltdx C1 cursor and source artifact.
- Process only newly closed minutes for the active N5 scope; never replay the
  full day on every poll.
- Test restart, lunch break, 14:59 close, provider failure, and cursor drift.
- C1/N3T or ActionExecuted failure must remain non-blocking for B1, N4,
  ActionEligible, and later N6 ActionEligible projection.

## N6 boundary

N6 is restored only after natural N1-N5 acceptance.  Its first acceptance is
the projection of canonical N5 `ActionEligible`; `ActionExecuted` projection is
additive and not an N6 startup prerequisite.

## Safety and recovery drills

- Create a separate disposable clone under C: and validate recovery from the
  immutable GitHub tag without deleting or touching the real worktree.
- After N1 and NAS acceptance, restore a disposable PostgreSQL instance from
  the Windows-origin backup plus WAL; never use a Mac database dump.
- Verify WSL cannot see D: and Codex/application accounts cannot write, delete,
  change ACLs, or take ownership there.
- Test NAS outage, WAL accumulation, checksum mismatch, TQ logout, port 17709
  loss, eltdx endpoint failover, and the 16:30-to-18:00 bounded readiness window.
