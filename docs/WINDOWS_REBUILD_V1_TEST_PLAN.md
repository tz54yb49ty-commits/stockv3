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
- Freeze routine `TDX-STOCK\ashare-ops` SID
  `S-1-5-21-2072264739-3883739137-88032818-1006` as Medium/non-admin/native SSH
  and elevated `TDX-STOCK\47894` SID
  `S-1-5-21-2072264739-3883739137-88032818-1002` as the distinct Administrators
  operator. Use 47894 only for the exact prepare admin allowlist; evaluate
  routine D denial only as ashare-ops. Do not create accounts or change
  passwords, groups or privileges.
- Read-only preflight native CPython 3.11 x64. If valid, perform zero Python
  mutation. If missing or damaged, allow exactly one official winget
  `Python.Python.3.11` machine-wide x64 install/repair at
  `C:\Program Files\Python311`, freezing the highest current safe 3.11.x
  version, official publisher, signer and SHA-256 first. Verify python.exe,
  PE x64, 3.11.x, pip and venv module. Do not create a business venv, resolve
  the project lock, or install project packages in W0; otherwise fail closed.
- Verify the eltdx installed source is commit
  `b2b94b967f478408848d007c83cc7155367c3aa9`.
- Verify the clean Git checkout commit and the release manifest.
- Install exact official EDB PostgreSQL 16.15-1 x64 under `D:\PostgreSQL\16`
  using package `PostgreSQL.PostgreSQL.16`, service `postgresql-x64-16`, transient
  installer identity `NT AUTHORITY\NetworkService`, final passwordless virtual
  account `NT SERVICE\postgresql-x64-16`, SHA-256
  `DE926FEFAD00E313E212CD438C0F04BF033E200099AD56C012724EFCEBED79F2`,
  Authenticode `Valid`, signer `EnterpriseDB Corporation`; initialize a new empty
  cluster at `D:\PostgreSQL\16\data`, and bind only to `127.0.0.1`.
  Execute only the exact staged installer
  `C:\AshareV3\staging\installers\postgresql-16.15-1-windows-x64-download-v1.exe`
  in interactive GUI mode; winget/unattended PostgreSQL execution is forbidden.
  Mac dump, record, source-version, and evidence imports must each remain zero.
  W0 must not create or migrate the `ashare_v3` business schema and must not
  write N1-N6 data.
- After empty bootstrap, stop the service, change StartName exactly once to the
  virtual account, set SID type UNRESTRICTED, grant exact D roots, remove every
  NetworkService ACE, then verify start and loopback. Enter the database-
  superuser-only password only in the elevated EDB GUI;
  never place it or its hash in CLI/argv/env/response files/history/transcripts/
  logs/evidence/screenshots. Local-account creation and retry are forbidden;
  NetworkService is not an allowed final PG16 identity.
- Confirm TdxW is logged in, `127.0.0.1:17709` is listening, and method-level
  TQ capability smokes pass.
- Dynamically freeze every current TaskName or TaskPath belonging to AshareV3,
  export each exact definition, then prove all frozen tasks Disabled. Record
  any historical/current count drift as quality evidence; never use a fixed
  task count as authority.
- Preserve the stopped legacy PostgreSQL 18 program and data unchanged; do not
  uninstall or delete it.  WSL shutdown is a separate native-control phase
  after sealed evidence and `RESTART_REQUIRED`.
- After native restart require only explicit `/mnt/c`, absent `/mnt/d`, and
  `/etc/wsl.conf` `[interop] enabled=false` plus `appendWindowsPath=false`.
  Verify Linux `ashare-codex` can read `/mnt/c` code. Native operations must use
  ashare-ops SSH; UAC installation must use the independent 47894 channel.

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

## W0 PostgreSQL virtual-identity 1639 recovery

Run only as `w0_postgresql_virtual_identity_1639_recovery`, bound to commit
`3160c7bee824a5cadcd7f63c78235a8b5c24c038`, tree
`08959a4190ca4d2dafe67cf7062625541657f171` and failed `sc.exe config` exit 1639.
Preflight proves Stopped, NetworkService StartName, SID UNRESTRICTED, existing
virtual ACL, NetworkService full-tree ACL count zero, loopback config and no
listener. Permit one `Invoke-CimMethod Win32_Service.Change` to
`NT SERVICE\postgresql-x64-16` with empty/null StartPassword and ReturnValue 0.
Verify StartName before one start; then require Running, UNRESTRICTED, only
`127.0.0.1:5432`, pg_isready and ACL count zero. Never modify config/ACL,
reinstall, use `sc.exe` for mutation, retry or restore NetworkService. Failure
leaves the service Stopped with evidence preserved and N1 blocked.

## W0 Python 3.11 per-user scope collision recovery

Use only `w0_python311_per_user_scope_collision_recovery_v1`, bound to parent
`9c8f80f9ca726fd00bdd30a625a4c5ed49cfddc1` and tree
`df8cbc4b01040542e2909b381014789f1d3b329b`. Freeze Git 2.55.0.windows.5
unchanged, exact PSF Python 3.11.9 installer path/hash/signature, 1603/0x643
PerUser Burn rollback, JustForMe/package-cache presence, absent Program Files
python, py reporting only Astral/3.12.12 and no installer/msiexec process. In
one 47894 session allow one official `/uninstall /quiet`; verify old per-user
3.11 absent (standalone launcher may remain) and machine python still absent;
then allow one exact all-users install vector. Accept only 0/3010 and verify
exact Program Files Python 3.11.9 x64, pip, venv and launcher entry. Never use
manual MSI, registry/cache/directory deletion, cleanup, retry, Store/3.12
authority, business venv/dependencies, or change Git/PG/D/WSL/Scheduler/N1-N6/
NAS/Mac. Failure preserves evidence and blocks N1.

## W0 PostgreSQL ReturnValue 22 recovery

Only `w0_postgresql_virtual_identity_22_recovery` may follow v6 commit
`0a64eb665433483a69e9134c222a1dabc03c1da2`, tree
`0f97f27c5a43d976e73f025e20d6b355f6ece494`, CIM ReturnValue 22, zero starts
and no identity change. Recheck Stopped, NetworkService StartName, SID
UNRESTRICTED and no 5432 listener. Permit one exact `sc.exe` process argument
vector: `config`, `postgresql-x64-16`, `obj=`,
`NT SERVICE\postgresql-x64-16`. Omit `password=` entirely so the native
ChangeServiceConfig lpPassword is NULL. Require exit zero and read-only
StartName verification before one start, then the existing final checks. Never
rerun v6/CIM, add a password or extra option, change ACL/config/install/logon
rights, retry or restore NetworkService. Failure remains Stopped and blocks N1.

### V9 Python orphaned dependency/AppSearch-cycle governance gate

Verify all nine governance files register
`w0_python311_orphaned_dependency_appsearch_cycle_recovery_v1` /
`w0_python311_orphaned_dependency_appsearch_cycle_recovery` and bind parent
`de7fc6ca0b2bed6a59b2130ddba8bcd67d7065d6`, tree
`cf247378267f8f47ddaf0a82a64fe4fcc6ad3c0c`. Freeze installer SHA
`5EE42C4EEE1E6B4464BB23722F90B45303F79442DF63083F05322F1785F5FDDE`, Burn log
SHA `466865F69D8C291FC299A0BEA36E6B1E45B116DF4D506672AB158D401E1B78B9`, path
log SHA `E4E8095B71B20C36DADC67384FF7FBDC989AE76FE429351E9F39615A4139CA08`, cached
MSI SHA `8A5C585D2A718BA73A4D1BB7A675DDBF56C016B6B851F2D32E07FF5DA48B1A4C`,
1603/0x643 and component `{38C34B30-BDE1-5985-9CB6-DD1712EEB4E2}`.
Verify AppSearch targets `TARGETDIR` and the frozen `DrLocator` rows form the
reported bidirectional cycle.

Focused tests prove `policy_version=9`, exact evidence and missing authority are
identical in AGENTS/Kernel and named throughout Compiler, Runtime Gate, Sandbox,
Trace, Test Suite and this plan. Exact evidence still REJECTs because Python
documents `/layout` only as offline payload download and does not support direct
internal-MSI recovery. Layout/direct MSI/bundle uninstall/machine install,
retry, manual PATH/registry/cache edit, cleanup, PG/D/WSL/Scheduler/Git/N1-N6/
NAS/Mac mutation and N1 handoff remain zero. Expected terminal state:
`BLOCKED_EVIDENCE_PRESERVED`.
