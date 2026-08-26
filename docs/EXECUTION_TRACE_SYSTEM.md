# Execution Trace System

## 1. Purpose

The Execution Trace System records every Codex decision path in A股监控系统 v3.

It exists to make every request auditable from normalized input through final execution status. The trace must show how the Execution Kernel, Runtime Gate, and Binding decision were reached, including both allowed execution and stopped execution.

This document defines the trace contract only. It introduces no runtime logic, no code implementation, no database write behavior, and no N1-N6 system change.

## 2. Required Trace Fields

Every trace entry must contain:

```yaml
execution_trace:
  kernel_input:
    intent: string
    layer_role: string
    affected_files:
      - string
    affected_resources:
      - string
    policy_id: string | null
    runtime_execution_requested: boolean
    data_flow: string
    risk_level: low | medium | high | critical

  kernel_decision:
    state: ACCEPT | REJECT | BLOCK | ESCALATE
    reason: string
    policy_id: string | null

  gate_decision:
    state: ACCEPT | REJECT | BLOCK | ESCALATE
    reason: string
    named_policy_evaluated: boolean
    named_policy_passed: boolean

  binding_decision:
    state: ACCEPT | REJECT | BLOCK | ESCALATE
    reason: string

  final_status: EXECUTE | STOP

  affected_files:
    - string

  affected_resources:
    - string

  layer_role: string

  risk_level: low | medium | high | critical
```

## 3. Trace Rules

```text
Every execution MUST be recorded.
Every STOP MUST be recorded.
Every REJECT/BLOCK must include reason.
No execution without trace entry.
```

Detailed rules:

1. If `final_status=EXECUTE`, the trace must include ACCEPT decisions from Kernel, Gate, and Binding.
2. If `final_status=STOP`, the trace must include the first decision that caused the stop.
3. If any decision is `REJECT` or `BLOCK`, its `reason` field is mandatory.
4. If any decision is `ESCALATE`, the trace must identify the layer or gate that owns the next decision.
5. A task may not proceed if its trace entry cannot be produced.
6. A runtime `ACCEPT` must record the exact `policy_id`, affected resources,
   named-policy evaluation result, primary/replay attempt counts, and fresh
   evidence hashes used by Kernel and Runtime Gate. A generic reason string is
   not a substitute for these fields. A bounded-evaluator `ACCEPT` must also
   record the exact four-table allowlist, observation DML scope predicates/
   insert columns, 081 grain, watermark/plan-hash/selection-CAS and same-scope/
   input/run-id replay verdict, same-hash unchanged verdict, surface
   exclusivity, observation change surface/dedup, Web function-only and virtual-
   executor observation disjointness, observation-preserving rollback, and the
   V2-dependent 081 rollback verdict.
7. The only currently valid runtime policy ids are
   `n6_strategy_center_display_only_bounded_run_once_v1`,
   `n6_strategy_center_display_only_scheduled_evaluator_v1`, and
   `n6_user_web_immutable_release_bounded_rebind_v1`, and
   `n6_strategy_center_schema_migration_maintenance_window_v1`, and
   `n6_strategy_center_post_081_v2_web_bounded_rebind_v1`, and
   `n6_strategy_center_post_083_v2_web_bounded_rebind_v1`, and
   `n6_strategy_center_post_081_v2_catalog_migration_window_v1`, and
   `n6_strategy_center_post_083_single_user_pending_v2_revision_v1`, and
   `n6_strategy_center_evaluator_quiesce_for_web_rebind_v1`, and
   `n6_strategy_center_pre_canary_web_write_quiesce_v1`, and
   `n6_immutable_release_install_bounded_v1`, and
   `n6_immutable_release_install_pre_rename_validator_recovery_v1`, and
   `n6_immutable_release_install_preflight_git_violation_recovery_v1`, and
   `n4_lifecycle_deactivation_state_columns_controlled_promotion_v1`, and
   `n4_lifecycle_inactive_mark_recovery_v1`; any other
   runtime policy id must trace `REJECT` and `STOP`.
8. A Web bounded-rebind `ACCEPT` must additionally record the exact label/plist,
   source and target Release identities and hashes, lineage verdict, frozen
   PID/PPID/argv/cwd/plist/environment/ownership evidence, primary and rollback
   attempt counts, readiness/route/stability timestamps, whether rollback was
   triggered, and proof that evaluator/executor and all forbidden effects stayed
   absent.
9. A scheduled-evaluator `ACCEPT` must additionally record the exact label/plist,
   immutable Release commit/tree/archive/manifest/filesystem hashes, auto
   runner/planner blobs, dependency lock/runtime-env and argv hashes, the frozen
   20260722 bounded-canary artifact, current-open-trade-date evidence, timezone
   and source-fingerprint attempt run id,
   `PGSERVICE`, all-users/per-user boundaries, DML tables, launchd/advisory-lock
   evidence, observation DML scope predicates/insert columns, 081 grain,
   watermark/plan-hash/selection-CAS and replay verdict, surface exclusivity,
   observation change surface/dedup, Web function-only and virtual-executor
   observation disjointness, before/readiness/rollback/concurrency hashes,
   whether rollback was triggered, proof that observation rows were preserved,
   the V2-dependent 081 rollback verdict, and proof that virtual executor and
   every forbidden effect stayed absent. Each tick trace must distinguish `current_open_execute`,
   `closed_day_noop`, and `drift_reject` without rewriting activation history.
10. An 081 maintenance-window `ACCEPT` must additionally record exact 081 and
    immutable Release hashes; Web/evaluator/virtual-executor labels, plist,
    Release, runner, role, ownership, and before-state; the Web-only write-flag
    delta; Web and evaluator state-driven teardown timestamps and attempt
    counts; routes/stability; evaluator PID/job absence; the four-table
    read-only watermark hash; immutable token path, mode, expiry, payload/file
    hashes; any pre-migration Web restore; and proof of zero migration,
    database-write/lock, evaluator-bootstrap, virtual-executor, N1-N5, queue,
    business, broker, or trading effect. Periodic PID/runs observations must be
    recorded separately from true configuration drift.
11. A post-081 V2 Web rebind `ACCEPT` must additionally record committed 081
    and absent 082/083 evidence; exact source/target Release hashes and
    V2/081/non-regression verdicts; Web PID/PPID/argv/cwd/plist/environment/
    ownership; strategy write `0` before, target, after, and rollback;
    evaluator job/PID absence; virtual-executor
    plist/Release/runner/role/ACL/object-boundary hashes and disjointness;
    primary/rollback attempt counts and timestamps; readiness/routes/stability;
    whether rollback occurred; and proof of zero database, migration,
    evaluator, virtual-executor, N1-N5, queue, business, broker, or trading
    effect. Periodic virtual-executor PID/runs observations must be separated
    from configuration drift.
11A. A post-083 V2 Web rebind `ACCEPT` must additionally record committed
    081/082/083/084 and schema/catalog evidence; the exact legacy source name;
    its short/full commit closure, tree, archive, git-ls-tree, manifest,
    filesystem, path/blob/mode, ownership, missing/extra/symlink/file-hardlink,
    immutable-attestation and current-Web verdicts; one-time rollback-only
    source use; the formal target name/commit and every immutable hash;
    source-delta, lineage, schema, V2 Web/API/UI/SSE, observation, direction,
    and trading-minute-freshness verdicts; Web PID/PPID/argv/cwd/plist/
    environment/ownership; strategy write `1` before, target, after, and
    rollback; the independent evaluator-quiesce artifact and evaluator job/PID
    absence with zero operations; virtual-executor
    `StartInterval=5`, plist/Release/runner/role-ACL/object-boundary hashes,
    disjointness, and zero operations; primary/rollback attempt counts and
    timestamps; readiness/routes/stability; and whether rollback occurred.
    Legacy-source reuse/mutation/target use and every database, migration,
    evaluator/executor, N1-N5, queue, business, broker, or trading effect must
    trace `REJECT` and `STOP`. Periodic executor PID/runs observations must be
    separated from configuration drift.
12. A post-081 V2 catalog migration `ACCEPT` must additionally record the exact
    phase and migration id; committed predecessor migrations and absent target/
    later migration; immutable Release and SQL hashes; strategy write `0`;
    evaluator job/PID absence; frozen virtual-executor plist/Release/runner/
    role/ACL/object-boundary hashes; phase-specific preflight facts; transaction
    identity, advisory lock, begin/commit, attempt count, before/after
    watermarks, postflight, and zero retry. An 082 trace records install-only
    constraints/index/functions/ACL and zero function calls or row writes. An
    083 trace records open trade date, zero pending/V2 selection items, unique
    active V1 coverage, and the exact four catalog transitions. Combined
    phases, wrong order, rollback in the forward request, or any forbidden
    business/trading effect must trace `REJECT` and `STOP`.
13. A post-083 pending-V2-revision `ACCEPT` must additionally record the frozen
    `pre_dml_guard_harness_recovery_v2` phase; exactly two ordered historical
    pre-DML harness identities (`42704/PUBLIC`, then `42601` from psql
    request-id non-expansion inside dollar-quoted `DO`); automatic aborts; zero
    official selection-function calls, revision/item DML, commits, and mutation
    attempts; absent persisted request ids; every equal before/after hash pair;
    audit-only `pg_catalog.aclexplode(COALESCE(proacl,
    pg_catalog.acldefault('f', proowner))).grantee=0` repair; unchanged official
    selection-function hash; the separate `READ ONLY` preflight; and the new
    request-id SHA-256. The request-id value and every token/secret must be
    redacted; the trace must record shell/driver parameter binding. It must then
    record the frozen principal/user/trade-date/predecessor/
    target/item scope; 081/082/083 postflight and V2 catalog hashes; strategy
    write `0`; evaluator absence; virtual-executor freeze and non-operation;
    zero pending/V2-item proof; official-function owner/user-isolation
    authority; request-id idempotence result; previous-revision CAS; exact
    mutation statement classes and zero `DO`/psql interpolation/dynamic SQL;
    new transaction identity and mutation-attempt count; exact revision/item
    DML; pending/pending postflight; other users and projection/change
    before/after hashes; and zero N1-N5, queue, business, broker, or trading
    effect. Any historical function call/DML/commit/mutation attempt, hash
    mismatch, changed failure order/reason, third error kind, third harness
    transaction, same request id, `DO`, psql interpolation, dynamic SQL, secret
    leakage, second mutation attempt, activation, Web write, compensation call,
    drift, extra scope/table, or retry must trace `REJECT` and `STOP`.
14. An evaluator-quiesce-for-Web-rebind `ACCEPT` must record post-083 and
    strategy-write=`1` evidence; exact evaluator label/plist/path/runner/
    Release/role/ACL/launchd ownership and before/after hashes; the single
    bootout attempt; PID/job absence timestamps; zero bootstrap/kickstart/
    kill/retry/automatic restore; frozen unchanged Web and virtual-executor
    configuration/ACL/object-boundary evidence; and proof of zero database,
    migration, evaluator execution, N1-N5, business, broker, or trading effect.
    Normal virtual-executor PID/runs cycling must be recorded separately from
    true configuration drift.

## 4. Trace Integrity Rules

```text
No missing records allowed.
No partial traces allowed.
No overwritten history allowed.
```

Detailed rules:

1. A trace entry must contain all required fields before execution is allowed.
2. A trace entry missing Kernel, Gate, Binding, or final status is invalid.
3. A trace entry must not be rewritten to change historical decisions.
4. Corrections must be appended as a new trace entry that references the prior entry.
5. Historical trace records must remain reviewable as evidence, even when superseded.

## 5. Replay Capability

The system must support full replay of the decision chain.

Replay must reconstruct:

```text
kernel_input
kernel_decision
gate_decision
binding_decision
final_status
affected_files
affected_resources
policy_id
layer_role
risk_level
```

Replay requirements:

1. Kernel evaluation must be reconstructable from `kernel_input`.
2. Runtime Gate evaluation must be reconstructable from `kernel_decision` and related Kernel output.
3. Binding evaluation must be reconstructable from Kernel and Gate decisions.
4. The final status must be explainable from the full decision chain.
5. A replay that cannot reconstruct Kernel + Gate + Binding is invalid.

## 6. Golden Rule

An `n6_immutable_release_install_bounded_v1` trace records the exact target and
staging paths, source commit/tree/archive/manifest/filesystem/attestation
hashes, owner/mode/ACL/xattr checks, pre-existing target absence, staging
uniqueness, validation and atomic rename timestamps, created-path cleanup and
the exact root-mode enable/restore timestamps plus proof that root owner/group/
ACL/xattr stayed frozen, group/other write was never enabled, final mode is
`0555`, and no existing Release, service, LaunchAgent, database, evaluator,
executor or business/trading object was touched.

An `n6_immutable_release_install_pre_rename_validator_recovery_v1` trace
records the exact BLOCKED attestation and sidecar paths/hashes, failure
status/stage/type/message/interpreter, zero prior rename/fallback/retry/
cleanup attempts, absent target, restored root, exact source hashes, existing-
Release fingerprints, and preserved staging-v1 path/device/inode/owner/mode/
count/ACL/xattr fingerprints. It must separately record the exact new
validator artifact directories, capability attestation and sidecar
paths/hashes/modes, `/usr/bin/xattr` binary hash,
protocol hash, generation/probe timestamps and complete capability verdict.
The trace must prove capability PASS preceded both Release-root chmod and
staging-v2 creation; capability failure must show both mutation attempts were
zero, root remained `0555`, capability evidence was sealed, and exact recovery
failure artifacts were written/sealed in FINALIZE before STOP. It must also record the sidecar-to-attestation hash equality, literal
validator executable hash, attestation-embedded executable/protocol equality,
no-duplicate-key verdict and before/after capability-artifact hashes.

Recovery execution trace fields include the exact staging-v2 path, every
materialization and full blob/path/mode/ACL/xattr-name/value validation
timestamp, exact xattr path/name/raw-value counts and canonical fingerprint,
including the release-content-manifest 6243-file/45-directory/6288-closure
reconciliation, the sole Release-root mode window, one atomic rename attempt,
the exact release-root dirfd identity, renameatx_np flags/result, exact
staging/target `501:20` ownership, final target/root modes and the immutable
recovery attestation hash. The root
restore timestamp must precede target postflight and recovery-attestation
writes. Every PASS or STOP must prove staging-v1 was not reused, modified,
renamed, deleted or cleaned; no fallback or second recovery occurred; and Git,
tests, ports, services, LaunchAgents, databases, evaluators/executors,
migrations, N1-N6 and business/trading objects were untouched. The prior
BLOCKED attestation is never overwritten. A pre-rename failure after staging-v2 creation must
additionally trace recursive `0444/0555` sealing, staging identity/metadata
fingerprints and zero writable residue before the Release root is restored. A
post-rename postflight failure must trace the immutable target fingerprint and
zero target modification/deletion attempts.

The trace must also bind the exact new recovery output directory, validation,
install-attestation and SHA-sidecar paths/hashes/modes/write counts and their
prior absence. It must prove the first output-path creation timestamp follows
Release-root restoration or confirmation at `0555` and the final sealed/
postflight boundary of the selected recovery outcome branch, including
capability failure; all output-path existence
checks during the root window, staging work, rename and Release postflight
must remain absent. It records rejected unknown request keys and proves no ordinary
rename, overwrite-capable rename or unbound output write occurred.
For each output failure point (root/directory creation, three writes and final
seal), STOP traces the exclusive/no-follow create result, recursive
`0444/0555` failure sealing, partial identity/hash evidence and zero writable
output residue.

An `n6_immutable_release_install_preflight_git_violation_recovery_v1` trace
binds the unique JSONL path, session/turn/message/tool-call identities, exact
turn line and byte interval, stable segment/prefix SHA-256 values, and
raw-line/arguments/output hashes for the sole Git call. It records the ordered
tool timeline, exact three read-only Git subcommands, zero mutating
Git/worktree operations and every zero pre-mutation counter. A current
whole-file JSONL hash is append-drifting and is never authority.

The later execution trace records zero Git and zero tests, direct raw-byte
verification of independently frozen current `AGENTS.md` and Kernel policy
block, direct filesystem preflight, capability-first ordering, fresh
staging-v2, full xattr raw-value validation, the sole root-mode window and
sole exclusive rename. Every outcome proves staging-v1 was untouched and no
prior-policy reuse, fallback, retry, cleanup, runtime, service, database,
evaluator/executor, migration, N1-N6 or trading action occurred. This
governance definition trace cannot contain recovery execution actions.

An `n4_lifecycle_deactivation_state_columns_controlled_promotion_v1` trace
records the frozen source base/endpoint/rollback commits and trees, exact
eight-path allowlist, source combined/rollback patch hashes, eight endpoint
blob ids, and both exact label/original-plist path/SHA pairs. Source commits
are marked `evidence_only=true` and never appear as final execution targets.

Before any bootout, the execution trace freezes the policy commit, its frozen
parent, two final promotion commits and final rollback. It records direct
parent edges, policy/final/rollback trees, final combined/rollback patch
hashes, exact final changed paths and all eight final blob comparisons. It
then records tracked/index clean proof, worker/child idle proof, both exact
bootouts, state-driven job/PID/child absence, the sole ff-only merge argv and
result, both original-plist bootstraps and postflight. Failure records only
the frozen rollback target with `rollback_execution_attempt_count=0`. The
trace also proves zero kickstart/manual execute/retry/push/checkout/rebase/
cherry-pick/plist-write/other-LaunchAgent/DB/message/queue/historical-event/
N2/N3/N5/N6/trading operations. This governance definition trace cannot
contain policy execution actions.

An `n4_lifecycle_inactive_mark_recovery_v1` trace records the frozen failed
HEAD/tree, stable commit/tree, content-only rollback commit/patch, exact eight
N4 paths, both label/plist path/SHA pairs, and the failed 09:34 target's zero
write counts. It freezes the complete post-policy direct-parent chain and all
N4 blob comparisons before any runtime mutation.

Each trace names exactly one phase and records two bootouts, state-driven
absence, one ff-only merge, two original-plist bootstraps and postflight. It
records corrected inactive current mark `normal`, retained previous mark and
projection `false/none`, plus zero schema/constraint/event changes. Combined
phases, automatic continuation/rollback, retry, manual execute, DB/message/
history and cross-layer operation counts must all be zero. A policy-definition
trace contains no policy execution action.

The current revision trace also records the exact `.git/ORIG_HEAD.lock`
permission failure/output hash, the unchanged Active HEAD/tree/index/tracked
state, one completed bootout/bootstrap per label, and zero DB/message effects.
It marks the prior four-commit chain evidence-only, records the four patch
hashes required of the regenerated chain, and proves escalated Git metadata
write authority before any later bootout. The definition trace contains no
runtime action.

An `n6_immutable_release_install_eacces_retry_v1` trace additionally records
the immutable prior-failure trace hash and `EACCES` errno, prior staging path
and validation hash, absent prior target/attestation, the distinct new staging
and target paths, both mode windows, and one rename timestamp. It must prove
the prior staging was never reused, modified or deleted and that both final
target and Release root are `0555`.

An `n6_immutable_release_install_host_eacces_remediation_v1` trace records the
host-trace path/hash and the two `EACCES` destinations, orphaned staging
validation hash, fresh path pair, both owner-write windows, one rename and
proof that no runtime/database/business object was touched.

An `n6_immutable_release_privileged_atomic_install_v1` trace records the
attested helper path/SHA/signature, root UID verification, release-root dirfd,
staging/target names, all three rename flags, one invocation, before/after
filesystem attestations and proof that no shell, metadata, runtime, database
or business operation occurred.

An `n6_immutable_release_privileged_materialize_and_install_v1` trace records
the V2 helper SHA/signature, exact d85df632 commit/tree/archive/manifest/
filesystem hashes and 6240-file/45-directory counts, orphan evidence, new
staging/target basenames, archive path/link/mode/count validation, one
renameatx_np invocation, immutable d85df632-named target attestation and
retained staging on failure.

An `n6_immutable_release_privileged_materialize_and_install_f67_v1` trace
records the dedicated helper source/binary SHA and signature, exact f67
commit/tree/archive/git-ls-tree/manifest/filesystem/bundle hashes, 6240/45 and
PAX 1/108 counts, distinct orphan evidence, fresh staging/target basenames,
safe extraction and sealed-mode results, the sole `renameatx_np` invocation,
target `0555` postflight and immutable f67 attestation. It also records zero
Release-runtime, service, database, evaluator, N1-N6 and trading operations.

No execution without a complete trace entry.

Strategy Center Gate3+ traces record the three reviewed N6 display-basis batch
identities (`for_trade_date`, `source_trade_date`, `source_run_id`, row count),
projection/card watermarks, membership as-of provenance, exact dynamic
principal/user/revision, evaluation time, run id, input watermark and plan
hash. They must never record calendar or N1-N5 raw-table authority.

`n6_strategy_center_pre_canary_web_write_quiesce_v1` traces record the
unchanged d85 Release identity, exact
Web before/target plist hashes, the sole flag `1 -> 0` delta, bootout/job
absence/bootstrap/readiness/stability timestamps, evaluator absence, zero
virtual-executor operations, and conditional rollback-to-flag-`1` evidence.

Scheduled evaluator traces additionally record at least twelve ticks,
pending-first/active-round-robin cursor progression, single-scope transaction
identity, deadline/backoff/overlap/restart evidence and cross-user write count.
Write-restore traces record exact Web flag `0 -> 1` and rollback-to-zero
evidence. Each remaining-user trace records one predecessor CAS and unchanged
other-user/projection/change hashes. V1-retirement traces record all-active-V2,
pending-zero, seven completed remaining-user gates, full replay/isolation/
projection/SSE hashes and the catalog-only mutation.

Strategy Center decommission traces apply the retirement lifecycle registry
first. A retired policy trace records `policy_status=RETIRED`,
`decision=REJECT`, and `final_status=STOP` without evaluating its historical
`ACCEPT` fields; the historical policy and trace evidence remain immutable.

An `n6_strategy_center_decommission_web_runtime_v1` `ACCEPT` trace records the
frozen source and immutable target Release identities/hashes, attested
Strategy Center route/UI/SSE/function/runtime-reference removal, non-Strategy
N6 non-regression, exact Web label/plist/environment, write flag `0` before,
after, and rollback, evaluator job/PID absence before/after and zero restore,
one primary bootout/bootstrap, readiness/stability timestamps, conditional
rollback counts, frozen virtual-executor boundary, and zero database,
other-service, heartbeat, N1-N5, business, broker, or trading operations. If
the optional evaluator artifact archive runs, the trace also records its new
path, allowed plist/state/log/history inventory, manifest/hash, read-only mode,
and proof it began only after Web stability.

An `n6_strategy_center_decommission_schema_archive_v1` `ACCEPT` trace records
the prior Web-decommission proof, exact transaction/advisory-lock identity,
fresh owner-only archive schema, exact six tables, every owned sequence/index,
Web/worker/`PUBLIC` `USAGE` revocation, exclusive trigger/function inventory
and removals, and each table's before/after row count, content hash, DDL, ACL,
and dependencies. It records protected-object invariance, zero drop/truncate/
row DML/retry/extra transaction, rollback SQL hash and retention deadline, and
`physical_deletion_automatically_scheduled=false`.

Physical deletion after 30 days and canary-heartbeat pause/removal trace
`REJECT/STOP` unless a future independent explicit policy and request exist.

A `runtime_hot_cleanup_archive_gated_disk_governance_v1` trace records exactly
one phase; exact Git/plist/process/capacity/calendar identities; cleanup job,
PID and child before/after state; every operation count; and zero forbidden
effects. Reclaim traces additionally bind the manifest, summary, allowlist and
restore-proof paths/SHA values, entry/count/byte totals, retained and active
lineage exclusions, candidate-writer proof, ordered per-entry revalidation and
unlink journal, each date-batch `df`, deleted/remaining entries, actual
allocated bytes removed, target decision, and archive restore path for every
deleted source. Snapshot traces bind each exact purgeable Time Machine local
snapshot and prove zero OS-update snapshot operations. Restore traces bind the
archive-required plist and absence of every direct-delete flag/token. A
partial or blocked phase retains its append-only evidence and never implies an
automatic retry.

## Windows rebuild W0 bounded trace contract

Every `windows_rebuild_w0_bounded_v1` trace is append-only and identifies
exactly one phase, either `w0_prepare_and_mutate` or
`wsl_shutdown_native_control`. Each entry records policy/baseline commit and
tree, phase, attempt number (exactly one), request authority, native/WSL
identity, UTC start/end timestamps, before/after evidence hashes, mutation
counts by exact resource and a final `ACCEPT`, `REJECT`, `RESTART_REQUIRED`,
`PASS` or `BLOCKED_EVIDENCE_PRESERVED` result. Missing, ambiguous, reordered,
overwritten or incomplete evidence is fail-closed and cannot authorize retry,
continuation, rollback or execution.

The prepare trace records the dynamically frozen current TaskName/TaskPath
AshareV3 inventory, before/after definitions and states, current count, any
prior-evidence count and their quality delta. It proves no historical fixed
count was execution authority, every frozen definition was exported and every
frozen task ended Disabled. It also records
legacy `postgresql-x64-18` service configuration/state/path fingerprints,
package identity/version/hash/signature, every exact C/D path and ACL/effective
access result, exact EDB 16.15-1 URL/version/SHA-256
`DE926FEFAD00E313E212CD438C0F04BF033E200099AD56C012724EFCEBED79F2`,
Authenticode `Valid`,
signer `EnterpriseDB Corporation`,
service `postgresql-x64-16`, transient `NT AUTHORITY\NetworkService`, final
`NT SERVICE\postgresql-x64-16`, empty-cluster proof,
loopback-only configuration, CPython 3.11 x64, TdxW, `127.0.0.1:17709`, and
the proposed WSL configuration. It records per-resource attempted/succeeded/
failed mutation counts and proves every forbidden count is zero, including
task delete/enable/create, legacy uninstall/file change, recursive delete,
overwrite, Mac import, Tushare/Mootdx, N1-N6, NAS, business write and
prepare-phase `wsl --shutdown`. A WSL configuration change ends only with
sealed pre-shutdown evidence and `RESTART_REQUIRED`; it never implies that the
shutdown phase ran.
The PostgreSQL installer trace also binds exact staged path
`C:\AshareV3\staging\installers\postgresql-16.15-1-windows-x64-download-v1.exe`
and records interactive GUI mode, with zero winget/unattended PostgreSQL
execution attempts.

Python trace fields record registry/launcher/Store-alias and executable
preflight facts and exactly one state: valid, missing or damaged native 3.11
x64. Valid records zero mutation. Missing/damaged may record one official
`Python.Python.3.11` machine-wide x64 install/repair at
`C:\Program Files\Python311`, frozen resolved safe 3.11.x version, publisher,
signer and SHA-256, attempt/result, and postflight python.exe existence, PE x64,
3.11.x, pip and venv-module results. It records zero second/retry, alias,
3.12/3.14, source/third-party, unknown uninstall, cleanup, business-venv and
project-package attempts. Failure is append-only blocked evidence.

PostgreSQL trace fields record GUI-summary identity, bootstrap completion,
service stop, one StartName transition, `UNRESTRICTED` SID type, virtual-account
SID resolution, exact D ACL before/after, NetworkService ACE removal/count zero,
service image/data path and verified start. The GUI password is database-
superuser-only and never a service-account password. The trace stores
only redacted GUI-entry completion and redaction-audit PASS, plus zero counters
for secret appearance in command line, argv, environment, response file,
history, transcript, log, evidence or screenshot. Local-account creation,
second transition/install attempt, early start, leakage or
incomplete redaction evidence is fail-closed and append-only.
NetworkService after bootstrap is fail-closed; final ACL count must be zero.

The shutdown trace requires and hash-binds that exact `RESTART_REQUIRED`
prepare entry. It records frozen evidence before connection loss, one native
control attempt, the exact `wsl --shutdown` timestamp/result, reconnect
identity/time, and post-reconnect proof that C is visible and D is absent. It
records zero additional Scheduler/service/installer/ACL/database/business
mutations and zero self-disconnect attempt from the current WSL/SSH session.
Missing native handoff, reconnect, drive-visibility proof, forbidden=0 proof,
or any second/combined phase attempt is incomplete evidence and therefore
fail-closed `REJECT/BLOCKED_EVIDENCE_PRESERVED`.

Identity trace fields separately record account, SID, token groups, integrity,
SSH login and role for routine `TDX-STOCK\ashare-ops` /
`S-1-5-21-2072264739-3883739137-88032818-1006` and elevated
`TDX-STOCK\47894` / `S-1-5-21-2072264739-3883739137-88032818-1002`. Every
admin mutation records the elevated actor SID and exact allowlisted operation;
every routine ACL postflight records the ashare-ops SID and D-denial results.
Operator D access is recorded separately and never counts as routine failure.
Trace counts account/password/group/privilege mutations, unknown/swapped/equal
SIDs, elevated-outside-prepare and current-WSL interop attempts at zero.

Restart trace records `/mnt/c` explicit visibility, `/mnt/d` absence,
`[interop] enabled=false`, `appendWindowsPath=false`, Linux `ashare-codex`
code access, ashare-ops native SSH channel and independent 47894 UAC channel.
Missing or combined identity/channel/isolation evidence is incomplete and
fail-closed.

The append-only `w0_postgresql_virtual_identity_1639_recovery` trace binds
commit `3160c7bee824a5cadcd7f63c78235a8b5c24c038`, tree
`08959a4190ca4d2dafe67cf7062625541657f171`, failed `sc.exe config`, exit 1639
and unchanged NetworkService StartName. It records before/after hashes, the
single attempt, exact pre-state, sole `Invoke-CimMethod Win32_Service.Change`
arguments without a secret, ReturnValue, StartName check, one start and final
state. Config/ACL/install, grant/remove/deny, `sc.exe` mutation, retry,
NetworkService restoration and N1 counts stay zero. Failure ends Stopped,
`BLOCKED_EVIDENCE_PRESERVED`, with N1 forbidden.

The append-only `w0_postgresql_virtual_identity_22_recovery` trace binds v6
commit `0a64eb665433483a69e9134c222a1dabc03c1da2`, tree
`0f97f27c5a43d976e73f025e20d6b355f6ece494`, ReturnValue 22, zero starts and
unchanged identity. It records fresh precheck hashes, one exact `sc.exe`
argument vector containing `obj=` and `NT SERVICE\postgresql-x64-16`, explicit
absence of `password=`, NULL lpPassword authority,
exit code, read-only StartName check, at most one start and final evidence.
V6/CIM rerun, password/extra argument, ACL/config/install/logon-right mutation,
retry, restoration and N1 counts remain zero. Failure is Stopped and
`BLOCKED_EVIDENCE_PRESERVED`.

The append-only `w0_python311_per_user_scope_collision_recovery_v1` trace binds
parent `9c8f80f9ca726fd00bdd30a625a4c5ed49cfddc1`/tree
`df8cbc4b01040542e2909b381014789f1d3b329b`; Git 2.55.0.windows.5 unchanged;
Python 3.11.9 installer path/hash/signature; 1603/0x643 Burn and dev-log facts;
PerUser JustForMe/package-cache evidence; absent
machine python; and no installer/msiexec process. It records one uninstall
`/uninstall /quiet` attempt/result, between-step registration/executable proof,
one exact machine install attempt/result accepting only 0/3010 and 3.11.9
x64/pip/venv/launcher postflight. All manual
MSI, registry/cache/directory delete, cleanup, retry, business venv/dependency,
Git/PG/D/WSL/Scheduler/N1-N6/NAS/Mac counters stay zero. Failure is append-only
`BLOCKED_EVIDENCE_PRESERVED` and no N1.

The append-only
`w0_python311_orphaned_dependency_appsearch_cycle_recovery_v1` trace binds
parent `de7fc6ca0b2bed6a59b2130ddba8bcd67d7065d6`/tree
`cf247378267f8f47ddaf0a82a64fe4fcc6ad3c0c`, v8 uninstall consumed once with
`0x643`, machine install zero, exact installer/log/cached-MSI hashes,
product/package/component IDs, missing source/targets, eight remaining MSI
registrations, stale PATH and the AppSearch/DrLocator cycle. It records
the cyclic AppSearch property `TARGETDIR`,
`policy_state=BLOCKED_MISSING_OFFICIAL_DIRECT_MSI_CONTRACT`, missing PSF
authority, `runtime_execution_allowed=false`, and zero layout/direct-MSI/
uninstall/machine-install/PATH/registry/cache/cleanup/business/W0/N1-N6
mutation counters. The only terminal trace is `BLOCKED_EVIDENCE_PRESERVED`;
there is no attempt, retry, cleanup, N1 handoff or executable command.

The append-only `w0_python311_isolated_uv_managed_install_v1` trace binds
parent `95af7b50c7032a74c5a196b1acaa935e89b29f60`/tree
`337c92c3db7d1cf591b7d1143a2385d27eb1be5f`; Windows 10 Pro 25H2
26200.9168 x64; ashare-ops SID/non-admin; Git; exact five absent targets;
process zero; and byte/hash snapshots of PATH, registry and legacy Python state.
It records exact directory/download/expand/install/find/venv attempts, uv ZIP
and uv.exe SHA, uv 0.12.1 PE x64, six process environment values, the uv
install request `cpython@3.11`, including `UV_PYTHON_INSTALL_BIN=0` and
`UV_PYTHON_NO_REGISTRY=1`,
built-in python-build-standalone artifact decision/checksum, managed patch/root/
python SHA/sys fields/module checks, and venv version/architecture/base-prefix/
pip/default-ensurepip inventory. Success records
`ISOLATED_NATIVE_CPYTHON311_READY`; failure records
`BLOCKED_EVIDENCE_PRESERVED` and preserves partial paths. Retry, cleanup,
admin/UAC, old MSI/bundle, PATH/registry, D/PG/WSL/Scheduler/Git/N1-N6/NAS/Mac,
business dependency and N1-handoff counters remain zero. V9 stays REJECT.
