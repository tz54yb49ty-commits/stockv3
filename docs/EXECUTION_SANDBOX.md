# Execution Sandbox

## 1. Purpose

The Execution Sandbox is a documentation-only system for A股监控系统 v3.

It simulates the full execution flow without making any real changes to the system. It is used to validate the decision chain before any actual write, runtime command, database operation, worker startup, or N1-N6 state mutation is allowed.

The sandbox validates:

```text
Execution Compiler output (DAG)
Kernel decisions
Gate enforcement
Binding validation
Trace generation
```

All sandbox outputs are hypothetical. The sandbox must not modify files, execute runtime logic, connect to databases, start workers, consume outbox events, perform rollback, or mutate N1-N6 state.

## 2. Sandbox Flow

```text
User Task
   ↓
Execution Compiler (DAG generation - simulated)
   ↓
Kernel Evaluation (simulated)
   ↓
Runtime Gate (simulated)
   ↓
Binding Check (simulated)
   ↓
Trace Generation (simulated)
   ↓
Diff Preview (NO REAL WRITE)
```

The sandbox flow mirrors the real enforcement chain but stops before any real file write or runtime side effect.

## 3. Sandbox Output

Sandbox output must include:

```yaml
sandbox_output:
  execution_plan:
    plan_id: string
    layer_role: runtime_control | N1_ingestion | N2_condition | N3_market_data | N4_trigger | N5_action | N6_user
    risk_level: low | medium | high | critical
    affected_files:
      - string
    affected_resources:
      - string
    policy_id: string | null
    runtime_execution_requested: boolean
    nodes:
      - id: string
        type: PLAN | VALIDATE | MODIFY | VERIFY | FINALIZE
        description: string
        layer_role: string
        affected_files:
          - string
    edges:
      - from: string
        to: string
        reason: string

  simulated_kernel_input:
    intent: string
    layer_role: string
    affected_files:
      - string
    affected_resources:
      - string
    policy_id: string | null
    data_flow: string
    risk_level: low | medium | high | critical

  simulated_kernel_decision:
    state: ACCEPT | REJECT | BLOCK | ESCALATE
    reason: string

  simulated_gate_decision:
    state: ACCEPT | REJECT | BLOCK | ESCALATE
    reason: string

  simulated_binding_decision:
    state: ACCEPT | REJECT | BLOCK | ESCALATE
    reason: string

  predicted_final_status: EXECUTE | STOP

  proposed_file_diffs:
    mode: read_only_preview
    files:
      - path: string
        diff_preview: string
```

## 4. Hard Rules

```text
NO file modification.
NO runtime execution.
NO database operations.
NO worker startup.
NO N1-N6 state mutation.
ALL outputs are hypothetical.
```

Detailed rules:

1. The sandbox must never write files.
2. The sandbox must never execute commands that change system state.
3. The sandbox must never connect to or mutate a database.
4. The sandbox must never start long-running services, bounded workers, or smoke workers.
5. The sandbox must never consume outbox, write inbox/checkpoint, execute rollback, trigger delivery, play voice, update mobile, update sim, update position, or perform real trading.
6. The sandbox must never alter N1-N6 facts, events, projections, schema, or runtime state.
7. The sandbox may only produce a read-only preview of proposed changes.

## 5. Sandbox Guarantee

The sandbox must ensure:

```text
execution safety validation
DAG correctness validation
decision chain consistency
rollback feasibility analysis
```

### 5.1 Execution Safety Validation

The sandbox verifies that a proposed task stays within the declared `layer_role`, `affected_files`, and allowed data-flow direction.

Any cross-layer mutation, runtime execution request, database operation, worker startup, or N1-N6 mutation must produce a simulated STOP outcome by default. The sandbox may predict `EXECUTE` for `n6_strategy_center_display_only_bounded_run_once_v1`, `n6_strategy_center_display_only_scheduled_evaluator_v1`, `n6_user_web_immutable_release_bounded_rebind_v1`, `n6_strategy_center_schema_migration_maintenance_window_v1`, `n6_strategy_center_post_081_v2_web_bounded_rebind_v1`, `n6_strategy_center_post_083_v2_web_bounded_rebind_v1`, `n6_strategy_center_post_081_v2_catalog_migration_window_v1`, `n6_strategy_center_post_083_single_user_pending_v2_revision_v1`, `n6_strategy_center_evaluator_quiesce_for_web_rebind_v1`, `n6_strategy_center_pre_canary_web_write_quiesce_v1`, `n6_immutable_release_install_bounded_v1`, `n6_immutable_release_install_pre_rename_validator_recovery_v1`, `n6_immutable_release_install_preflight_git_violation_recovery_v1`, `n4_lifecycle_deactivation_state_columns_controlled_promotion_v1`, `n4_lifecycle_inactive_mark_recovery_v1`, `n6_immutable_release_install_eacces_retry_v1`, `n6_immutable_release_install_host_eacces_remediation_v1`, or `runtime_hot_cleanup_archive_gated_disk_governance_v1` only when its simulated Kernel and Runtime Gate independently pass every machine-readable condition of the selected policy. The sandbox itself still performs no command, database connection, file mutation, service restart, or write.

`n6_immutable_release_privileged_atomic_install_v1` is an additional named
exception only when its simulated Kernel and Runtime Gate independently pass.

`n6_immutable_release_privileged_materialize_and_install_v1` is an additional
named exception only when its simulated Kernel and Runtime Gate independently
pass every fixed-archive, one-staging and one-promotion requirement.

`n6_immutable_release_privileged_materialize_and_install_f67_v1` is a separate
simulated exception only when its dedicated helper path and every frozen f67
commit/tree/archive/git-ls-tree/manifest/filesystem/bundle hash, 6240/45
count, PAX 1/108 count, one-fresh-staging and one-promotion requirement pass.
The sandbox predicts `REJECT` for d85-helper reuse, old staging reuse, path or
hash drift, unsafe archive entries, retries, metadata expansion, runtime,
database, N1-N6 or trading operations. The sandbox performs no real action.

For `runtime_hot_cleanup_archive_gated_disk_governance_v1`, Sandbox predicts
`EXECUTE` only for one selected phase with every Kernel and Runtime Gate field
present. Reclaim simulation uses only the SHA-bound exact allowlist, models
per-entry identity/source/archive hash revalidation, exact unlink plus durable
journal, fixed family/date order, per-date `df` measurement and the 250 GiB
stop. Missing archive/restore evidence, retained/active/writer overlap,
symlink/path drift, directory inference, glob/recursive deletion, cross-layer
or business-service operation, database/snapshot mixing, retry, or a
policy-definition execution predicts `STOP/REJECT`. The sandbox itself never
unlinks a file or changes a service.

### 5.2 DAG Correctness Validation

The sandbox verifies that the simulated execution plan:

```text
contains PLAN -> VALIDATE -> MODIFY -> VERIFY -> FINALIZE
places VALIDATE before every MODIFY
contains no cycles
contains no cross-layer node
contains no node outside affected_files
```

### 5.3 Decision Chain Consistency

The sandbox verifies that simulated decisions are consistent:

```text
Kernel ACCEPT is required before Gate evaluation can allow execution.
Gate ACCEPT is required before Binding can allow execution.
Binding ACCEPT is required before predicted_final_status can be EXECUTE.
Any REJECT / BLOCK / ESCALATE produces predicted_final_status=STOP.
```

For `n6_strategy_center_display_only_bounded_run_once_v1`, the simulated output
must also include the policy id, exact principal/user/selection-revision/current-
trade-date scope, allowed write tables, primary/replay attempt limits, immutable
Release evidence, dry-run/watermark/plan hash, ACL, CAS, rollback, and every
forbidden-field result. When the virtual executor is loaded or running, it must
also model the exact post-083 Gate2/revision-20/current-20260723 coexistence
mode; zero pre-Gate2 dry-run/primary/replay attempts; frozen
label/plist/Release/runner/PGSERVICE/role-ACL/object-boundary hashes; no Strategy
Center table write, formal-function execute, or code-reference authority; exact
dry-run -> primary -> same-input replay order; and zero executor operations.
Any executor operation or configuration/ACL/object/runner/Release/label drift
predicts `STOP`; normal existing `StartInterval=5` PID/runs cycling alone does
not. Missing or false evidence predicts `STOP`; the sandbox must not infer or
fabricate a passing field. The model uses the exact four-table evaluator DML
allowlist and predicts `STOP` for a fifth table, missing observation scope
predicate/insert column, non-081 grain, cross-scope/date write, dual surface,
duplicate change, non-observation change surface, replay drift, Web/virtual-
executor observation write authority, executor observation code reference,
observation-deleting rollback, or V2-dependent 081 schema rollback.

For `n6_user_web_immutable_release_bounded_rebind_v1`, the simulated output must
also include the exact label/plist/port, one source and one target Release,
commit/tree/archive/manifest hashes, non-regressing lineage, immutable-content
proof, affected resources and operations, frozen PID/PPID/argv/cwd/plist/
environment/ownership, state-driven teardown, primary and rollback attempt
limits, readiness/routes/stability, evaluator/executor guards, and every
forbidden-field result. Ownership ambiguity, drift, extra resource, missing
evidence, or rollback not tied to a proven primary failure predicts `STOP`; the
sandbox must not infer or fabricate a passing field.

For `n6_strategy_center_display_only_scheduled_evaluator_v1`, the simulated
output must also include current-request automatic-evaluator authorization; the
frozen 20260722 single-user bounded dry-run/primary/same-input replay, projection,
and SSE PASS artifact; one exact immutable Release with commit/tree/archive/
manifest/filesystem hashes; the exact auto runner/planner blobs, dependency
lock/runtime-env hashes, and planner-derived argv; exact label,
plist, and `StartInterval=5`; `PGSERVICE=n6_strategy_worker`; current-open-day
proof and closed-day-no-DML behavior; per-user all-users isolation; the exact
four-table DML list; complete observation scope/grain/surface/dedup/replay
evidence; both no-overlap guards; before/readiness/rollback/concurrency
evidence; Web function-only, virtual-executor observation disjointness,
observation-preserving exact-label/plist rollback, V2-dependent 081 rollback
rejection, and every forbidden-field result. Missing evidence, drift,
non-current/non-open write authority, extra
runner argument/resource/table/LaunchAgent, or overlap predicts `STOP`; the
sandbox must not infer or fabricate a passing field.

For `n6_strategy_center_schema_migration_maintenance_window_v1`, the simulated
output must include exact current-request authorization; exact 081 and immutable
Release hashes; Web/evaluator labels, plists, runners, roles, ownership, and
before-state; the single Web strategy-write-flag delta; one Web
bootout/bootstrap pair; one evaluator bootout and zero evaluator bootstrap;
state-driven teardown; Web readiness/routes/stability; evaluator absence; the
four-table read-only watermark boundary; immutable maintenance-token fields,
hashes, mode, and expiry; virtual-executor configuration freeze and object
disjointness; recovery-phase limits; and every forbidden-field result.

Missing/expired/drifted evidence, a migration attempt, database write/lock,
082/083, virtual-executor operation, old-evaluator restore, extra service,
fixed sleep, kill/kickstart, retry, N1-N5 or business/trading effect predicts
`STOP`. A normal periodic PID/runs change without label/plist/Release/runner/
role/object drift must not by itself predict `STOP`. The sandbox must not infer
or fabricate a passing field.

For `n6_strategy_center_post_081_v2_web_bounded_rebind_v1`, the simulated output
must include exact current-request authorization; committed 081 and absent
082/083 evidence; one exact Web, source Release, and target V2 Release; all
commit/tree/archive/manifest/filesystem hashes; V2 Web/API/UI/SSE, observation,
direction, trading-minute freshness, 081 compatibility, and non-regression
proof; Web ownership and strategy write `0` before/target/after/rollback;
evaluator job/PID absence; frozen virtual-executor
plist/Release/runner/role/ACL/object-boundary hashes and Strategy Center write
disjointness; one primary bootout/bootstrap pair, zero retries, bounded
readiness/stability, one conditional frozen-source rollback, and every
forbidden-field result.

Missing or drifted evidence, strategy write `1`, an evaluator operation, a
virtual-executor operation, database/migration request, mutable Release, extra
service, repeated attempt, N1-N5, queue, business, broker, or trading effect
predicts `STOP`. Normal virtual-executor StartInterval PID/runs cycling alone
must not predict drift. The sandbox must not infer or fabricate a passing field.

For `n6_strategy_center_post_083_v2_web_bounded_rebind_v1`, the simulation must
include current-request authorization; committed 081/082/083/084 and frozen
schema/catalog evidence; one exact legacy source basename
`20260724_042200__a1dc7350`; its full-commit/tree/archive/git-ls-tree/manifest/
filesystem/blob-mode-path/ownership/immutable closure; one-time rollback-only
use; one formal 40-character target with name/commit binding and complete
immutable, source-delta, non-regression, V2, and schema evidence; strategy write
`1` before/target/after/rollback; a passed independent evaluator-quiesce gate
with job/PID absent and zero evaluator operations; and frozen, write-disjoint
virtual-executor `StartInterval=5` evidence with zero executor operations.

The simulation may predict one exact-Web bootout/bootstrap, state-driven
teardown, 60-second readiness, 30-second stability, and one conditional exact
legacy-source rollback. Missing or drifted evidence, another/reused/mutated
legacy source, legacy target use, a short target, evaluator or executor
operation, strategy-write `0`, database/migration, extra service, retry,
N1-N5, queue, business, broker, or trading effects predicts `STOP`. Normal
virtual-executor PID/runs cycling alone does not predict drift. The sandbox
must not infer or fabricate a passing field.

For `n6_strategy_center_post_081_v2_catalog_migration_window_v1`, the simulated
output must select exactly one phase. The 082 simulation must prove committed
081, absent 082/083, pending count zero, exact Release/SQL hashes, and an
install-only constraint/index/function/ACL diff with no function call or row
mutation. The 083 simulation must prove committed 081/082, absent 083, passed
082 postflight/ACL, an open trade date, pending count zero, V2 selection item
count zero, unique active V1 coverage, and exactly four catalog transitions.

Both simulations must keep strategy write `0` and evaluator absent, freeze
write-disjoint virtual-executor evidence, use one explicit transaction and
forward attempt with zero retry, and reserve rollback for a separate request.
Combined phases, wrong order, compensation calls, selection/projection/change
writes, Web/evaluator/executor operation, extra migration/service, business
DML, N1-N5, broker, or trading effects predict `STOP`. Normal executor
StartInterval PID/runs cycling alone does not predict drift.

For `n6_strategy_center_post_083_single_user_pending_v2_revision_v1`, the
simulation must first prove `pre_dml_guard_harness_recovery_v2`: exactly two
ordered, automatically aborted historical pre-DML harness transactions,
SQLSTATE `42704` with `role "PUBLIC" does not exist`, then SQLSTATE `42601`
because the psql request-id variable inside dollar-quoted `DO` did not expand.
Both must have zero official selection-function calls, zero revision/item DML,
zero commits, no persisted request id, zero mutation attempts, and identical
declared before/after hashes. It may model only an ACL audit-guard correction
using
`pg_catalog.aclexplode(COALESCE(proacl,
pg_catalog.acldefault('f', proowner))).grantee=0`; the official selection
function remains unchanged. A fresh independent `READ ONLY` preflight completes
all complex validation before a new request id is supplied through shell/driver
parameter binding. Only the request-id hash is auditable; token/secret logging
is forbidden. These precede the exact
1/1/15/revision_no-5/current-20260723 canary, committed 081/082/083 postflight
hashes, active V2 catalog, strategy write `0`, evaluator absence, and
frozen/unoperated virtual executor. It must model zero pending/V2 items, the
unique active V1 predecessor, unchanged package keys, package_1/v1 -> v2 only,
owner/user-isolated official-function authority, request-id idempotence,
previous-revision CAS, one new transaction, at most one mutation attempt, and
zero retries. The mutation transaction may contain only BEGIN/SET/advisory-lock
SELECT/one official function SELECT/read-only postflight SELECT/COMMIT; `DO`,
psql variable interpolation, dynamic SQL, and complex validation predict
`STOP`.

The predicted diff is exactly one pending/pending revision and one package_1/v2
item. Activation, Web PUT/write enable, multi-scope, non-current day,
predecessor drift, compensation call, projection/change/catalog/schema/extra
table writes, evaluator/executor operation, N1-N5, queue, business, broker, or
trading effects predict `STOP`. Any historical function call, revision/item
DML, commit, persisted or reused request id, mutation attempt, before/after
hash mismatch, changed failure order/reason, third error kind, third harness
transaction, official-function change, non-audit guard change, secret leakage,
or second mutation attempt also predicts `STOP`. The sandbox must not infer a
missing field or use the governance session as runtime authority.

For `n6_strategy_center_evaluator_quiesce_for_web_rebind_v1`, the simulation
must bind post-083 state, strategy write `1`, one exact evaluator label and
bootout target, frozen plist/path/runner/Release/role/ACL/ownership/before
state, and state-driven PID/job absence. It predicts `STOP` for evaluator
execution, bootstrap, kickstart, kill/signal, retry, automatic restore, Web or
virtual-executor operation, ownership/configuration/hash drift, or any
database, migration, selection/projection/change, queue, N1-N5, business,
broker, or trading path. Normal configured virtual-executor PID/runs cycling
alone does not predict drift. The governance session itself performs no
bootout.

### 5.4 Rollback Feasibility Analysis

Because the sandbox performs no real writes, rollback is normally a no-op.

For every proposed file diff, the sandbox must still identify whether the hypothetical change would be reversible by discarding the proposed diff before write. If a proposed change cannot be represented as a reversible read-only diff preview, the sandbox must return predicted_final_status=STOP.

## 6. Diff Preview Contract

Diff preview is read-only.

It may describe:

```text
new file path
modified file path
proposed added lines
proposed removed lines
rollback preview
```

It must not:

```text
write the diff
apply the patch
touch the filesystem
change runtime state
```

## 7. Golden Rule

For `n6_immutable_release_install_bounded_v1`, Sandbox predicts `EXECUTE` only
for one explicitly authorized, already-attested target Release that does not
exist before the run. Staging must be unique and under the same Release root;
all content/hash/metadata checks must pass before one atomic rename. The only
temporary root metadata transition is one owner-write `0555 -> 0755 -> 0555`
window with frozen owner/group/ACL/xattr and no group/other write. Failure must
restore `0555` before returning. The only persistent predicted diff is the newly created target and install artifacts. Existing
Releases, services, LaunchAgents, databases, evaluators and business data are
untouchable. Failure cleanup is limited to newly created paths.

Sandbox simulation is not execution.

For `n6_immutable_release_install_pre_rename_validator_recovery_v1`, Sandbox
predicts `EXECUTE` only for the exact hash-bound aa6d19c BLOCKED pre-rename
failure, unchanged source and existing-Release fingerprints, absent target,
restored `0555` root, and the exact preserved staging-v1 identity and
metadata/xattr fingerprints. The one later recovery simulation must first
generate exactly one SHA-bound xattr-validator capability attestation and
sidecar. Capability failure predicts STOP before any root chmod or staging-v2
creation, but first predicts root confirmation at `0555` plus creation and
sealing of exact recovery failure artifacts in FINALIZE. Only capability PASS may predict one fresh staging-v2
materialization, complete blob/path/mode/ACL/xattr-value validation against
the exact release-content-manifest-derived Kernel path set, record count,
name, raw-value and canonical fingerprint, one root write window and one
exclusive same-dirfd renameatx_np promotion with EXCL/NOFOLLOW_ANY/BENEATH.
The predicted persistent diff contains only the new target and exact new
capability/recovery evidence and install-attestation paths;
staging-v1 remains unchanged evidence. Missing capability proof, partial
validation, old-staging reuse/mutation/deletion/cleanup, another staging,
fallback, second recovery, Git/test/port/service/LaunchAgent/database/
evaluator/executor/migration/N1-N6/business/trading activity predicts
`REJECT`. Unknown request keys, ordinary/overwrite rename, owner/group drift,
unbound output paths or output overwrite also predict `REJECT`. The governance
definition gate always simulates `STOP` for recovery
execution. Any predicted pre-rename failure after staging-v2 creation must
first seal all created staging-v2 entries to `0444/0555`, freeze
identity/metadata evidence and restore the Release root; a writable failed
staging predicts `REJECT`. A post-rename postflight failure preserves the
immutable target as evidence and predicts no target modification or deletion.
On the success branch, root restoration immediately follows the sole rename
attempt and precedes every target postflight or attestation write.
The simulation must defer creation of every recovery output path until the
root is restored or confirmed unchanged at `0555` and the selected recovery
outcome branch, including capability failure, has finished sealing and
postflight; an output path present during the root
window, staging work, rename or Release postflight predicts `REJECT`.
Any failure from output-root creation through final output seal must predict
exclusive/no-follow partial-file handling, recursive `0444/0555` sealing,
partial identity/hash evidence and zero writable output residue before STOP.

For `n6_immutable_release_install_preflight_git_violation_recovery_v1`,
Sandbox predicts `EXECUTE` only for the unique frozen pre-mutation turn
segment and exact single read-only Git tool-call history. Simulation requires
zero historical Git/worktree mutation and zero filesystem/runtime mutation,
then models a later gate with no Git and no tests. Governance authority comes
only from the frozen current `AGENTS.md` raw-byte hash, policy-block raw-byte
hash, stable session segment/prefix hashes and direct filesystem evidence.
Capability failure predicts FINALIZE-A then STOP without root chmod or
staging-v2. Capability PASS predicts one fresh staging-v2, complete
blob/path/mode/owner/ACL/xattr-value validation, one root write window and one
exclusive same-dirfd rename. Staging-v1 mutation, prior-policy reuse, fallback,
retry, cleanup, service/runtime/database/N1-N6/trading activity, Git or tests
predict `REJECT`; this governance gate always predicts STOP for execution.

For `n4_lifecycle_deactivation_state_columns_controlled_promotion_v1`,
Sandbox treats the frozen source endpoint/rollback only as non-executable
content evidence. It predicts `EXECUTE` only when an independent later gate
has frozen a policy commit whose parent is `8229124a`, exactly two direct-child
promotion commits and a direct-child rollback whose tree equals the policy
commit. Simulation recomputes the fixed eight paths, endpoint blobs,
combined/rollback patch hashes and two exact label/original-plist bindings.

The safe simulated path is two exact bootouts, state-driven job/PID/child
absence, one ff-only merge to the final tip, and two original-plist
bootstraps. Source commits used as execution targets, dirty tracked/index
state, plist/worker/child drift, another path/blob/patch/plist/label, fixed
sleep, kickstart, manual execute, retry, non-ff merge, push, checkout/rebase/
cherry-pick, automatic rollback, DB, message/queue, historical-event,
N2/N3/N5/N6 or trading work predicts `REJECT`. Failure predicts only rollback
target reporting, never rollback execution. This definition gate always
predicts STOP for execution.

For `n4_lifecycle_inactive_mark_recovery_v1`, Sandbox simulates exactly one
phase per request. It verifies the post-policy direct-parent chain, the stable
eight-file rollback restore, the corrected `normal` inactive current mark with
previous evidence retained, and a code rollback that restores the
rollback-restore N4 tree. The only executable shape is two exact bootouts,
state-driven absence, one ff-only merge and two original-plist bootstraps.
Phase combination, automatic continuation/rollback, retry, schema/constraint
change, manual execute, DB/message/history or cross-layer work predicts
`REJECT`. The policy-definition gate always predicts STOP.

The current revision also simulates the frozen `.git/ORIG_HEAD.lock`
permission failure and requires zero ref/tree/index/tracked mutation plus both
original-plist restorations. It predicts STOP unless a fresh post-revision
four-commit chain reproduces every frozen patch hash and Git metadata write
authority is verified before any bootout. Prior-target reuse and an
unauthorized merge probe predict `REJECT`.

For `n6_immutable_release_install_eacces_retry_v1`, Sandbox predicts `EXECUTE`
only after a frozen initial `EACCES` failure with unchanged prior staging and
restored root. It predicts one distinct staging/target pair, one root write
window, and one staging-root write window surrounding one atomic rename. Any
prior-staging reuse, non-EACCES cause, target exposure, drift, second retry or
runtime/database/business action predicts `REJECT`.

For `n6_immutable_release_install_host_eacces_remediation_v1`, Sandbox predicts
`EXECUTE` only from a hash-bound host trace proving both same-parent and `/tmp`
`EACCES` failures for a `0555` staging. It predicts one fresh staging/target
and one staging-root mode window; orphaned staging reuse or modification,
missing trace, retries and runtime/database/business actions predict `REJECT`.

For `n6_immutable_release_privileged_atomic_install_v1`, Sandbox predicts
`EXECUTE` only for one attested helper SHA/signature and one fixed-root
parent-dirfd `renameatx_np` using all exclusive/no-follow/beneath flags. Any
fallback, arbitrary path, metadata mutation, repeat, service, database or
business action predicts `REJECT`.

For `n6_immutable_release_privileged_materialize_and_install_v1`, Sandbox
predicts `EXECUTE` only for the exact hash-bound d85df632 archive/manifest,
source tree, filesystem validation SHA, 6240-file/45-directory counts, one
attested V2 helper and one new staging retained on failure. Unsafe archive
entry, another source/hash/count, path escape, symlink/hardlink, mode/count
drift, malformed or unknown PAX/type records, retry or any
runtime/database/business operation predicts `REJECT`. Only strictly framed
PAX `g`/`x` records with `comment`/`path` keys and the frozen Git archive
input-to-sealed-output mode matrix predict `EXECUTE`.

No real change is allowed inside the sandbox.

For Strategy Center Gate3+,
`n6_strategy_center_pre_canary_web_write_quiesce_v1` sandbox simulation
predicts `EXECUTE` only when
an independently authorized exact-Web pre-canary gate has changed strategy
write `1 -> 0` on the unchanged d85 Release while evaluator and virtual
executor operation counts remain zero, and
the stock/index/board reviewed N6 display-basis latest complete singleton
batches agree on `for_trade_date`, source/card watermarks and membership as-of
provenance are frozen, and no calendar or N1-N5 raw-table authority appears.
It models a dynamic single-scope bounded canary, one-scope-per-tick exact
five-second evaluator with at least twelve stable ticks, one exact-Web flag
restore, seven separate remaining-user CAS gates, and a final catalog-only V1
retirement. Missing natural current-date events, all-users mutation, a second
attempt, cross-user write, evaluator/executor drift or operation, incomplete V2
rollout, N1-N5, database expansion, or trading effect predicts `REJECT`.

For Strategy Center decommission simulation, the retirement lifecycle registry
is evaluated first. Every retired policy predicts `STOP/REJECT`. The Web
decommission policy predicts `EXECUTE` only for one exact-Web Release rebind
with write `0`, evaluator absent and unrestored, bounded readiness/stability,
conditional frozen-source rollback, optional post-stability read-only artifact
archive, and zero database/virtual-executor/other-service/heartbeat effects.
The schema archive policy predicts `EXECUTE` only for a separate single
transaction over the exact six tables and owned sequences/indexes, new
owner-only schema, required `USAGE` revocations, exclusive trigger/function
removal, full evidence, protected-object invariance, and a dedicated 30-day
rollback. Drop/truncate/row DML, retry, gate combination, automatic deletion,
or missing evidence predicts `STOP/REJECT`.

Simulation never performs either decommission policy. Physical deletion after
30 days and canary-heartbeat pause/removal remain outside both models and
always predict `STOP` without a new independent policy.

## Windows rebuild W0 bounded simulation

For `windows_rebuild_w0_bounded_v1`, Sandbox Simulation is a read-only proof
that must complete before any host mutation. The policy-definition governance
session always predicts `REJECT`; a simulation `PASS` is not execution
authority and does not change `POLICY_READY_NOT_EXECUTED`. A later, explicitly
authorized, independent `runtime_control` session may simulate exactly one
attempt of exactly one phase: `w0_prepare_and_mutate` or
`wsl_shutdown_native_control`. The phases are mutually exclusive, cannot be
combined or retried, and form only the one-way order
`w0_prepare_and_mutate -> RESTART_REQUIRED -> wsl_shutdown_native_control`.

The prepare-phase model requires mutation count zero before simulation and
freezes the baseline commit/tree, identity and effective access, exact paths,
existing-path conflicts, installer version/hash/signature, process/service
inventory and the exact AshareV3 scheduled-task set. It predicts `EXECUTE`
only for export plus disable of exact matching tasks (never delete, create or
enable), stop plus disable of `postgresql-x64-18` (never uninstall or touch
its program/data), packages `Git.Git` and `PostgreSQL.PostgreSQL.16` with
PostgreSQL >=16.14, and these exact database resources:
`D:\PostgreSQL\16`, `D:\PostgreSQL\16\data`,
`D:\PostgreSQL\backup-staging`, service `AshareV3-PostgreSQL-16`, identity
`NT SERVICE\AshareV3-PostgreSQL-16`, and `listen_addresses=127.0.0.1`.
The new cluster must be empty: Mac dump/record/source_version/evidence imports,
business database/schema work and N1-N6 writes all remain zero.

The same model permits only `C:\AshareV3\app`, `config`, `runtime`, `logs`,
`seed-inbox`, `evidence` and `staging` below `C:\AshareV3`; it proves the
dedicated non-interactive PostgreSQL identity is limited to the three exact D
resources and that the non-admin application/Codex identities are denied D
read, list, write, create, delete, permission-change and take-ownership
rights. It also proves native CPython 3.11 x64, TdxW and
`127.0.0.1:17709`, and models WSL configuration with only C visible and D
hidden after restart. Any path conflict, unproven ACL/effective access,
unexpected service/task/resource, destructive or overwrite operation,
Tushare/Mootdx, Mac import, N1-N6, NAS, business write, or prepare-phase
`wsl --shutdown` predicts fail-closed `REJECT` with evidence preserved.

The native shutdown-phase model predicts `EXECUTE` only after a sealed
`RESTART_REQUIRED` result and frozen pre-shutdown evidence from the prepare
phase. It simulates one native-control `wsl --shutdown`, evidence durability
before connection loss, and post-reconnect proof that C is visible and D is
absent. A current WSL/SSH session attempting to disconnect itself, missing
native handoff, missing reconnect proof, phase combination or any additional
mutation predicts fail-closed `REJECT`. Even when either simulation passes,
Sandbox performs no host action and grants no permission to execute W0.
