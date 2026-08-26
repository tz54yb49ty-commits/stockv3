# Execution Runtime Gate

## 1. Purpose

The Runtime Gate is the final enforcement gate after Execution Kernel evaluation.

It exists to ensure that a task approved by the Execution Kernel is still safe to proceed at runtime-control level. The Gate does not execute commands, start workers, connect to databases, consume outbox events, perform rollback, or change N1-N6 behavior.

This document defines the gate contract only. It introduces no runtime logic and no system implementation.

## 2. Input

The Runtime Gate accepts only `kernel_output`.

```yaml
kernel_output:
  kernel_decision:
    state: ACCEPT | REJECT | BLOCK | ESCALATE
    reason: string
    policy_id: string | null

  kernel_input:
    intent: string
    layer_role: string
    affected_files:
      - string
    affected_resources:
      - string
    policy_id: string | null
    data_flow: string
    risk_level: low | medium | high | critical

  evidence:
    kernel_evaluated: boolean
    cross_layer_violation_detected: boolean
    runtime_execution_requested: boolean
    named_policy_evaluated: boolean
    named_policy_passed: boolean
```

No raw user request, inferred task, or unstated assumption may bypass `kernel_output`.

## 3. Decision States

### ACCEPT

The Kernel exists, the Kernel returned `ACCEPT`, no cross-layer violation is present, and the requested action remains within approved file/resource and layer boundaries. Runtime execution must be absent unless the Kernel selected and fully passed a named machine-readable policy, including the Strategy Center bounded run-once, scheduled evaluator, Web rebind/quiesce, migration, reviewed-date, write-restore, single remaining-user migration, or final V1-retirement policies listed in `AGENTS.md`.

Result: execution may proceed only within the approved scope.

### REJECT

The request violates a hard runtime gate rule.

Examples:

```text
missing Kernel output
Kernel was not evaluated
cross-layer violation
runtime execution request
attempt to bypass the Gate
```

Result: stop immediately.

### BLOCK

The request cannot be safely evaluated because required gate evidence is missing or incomplete.

Examples:

```text
kernel_output is incomplete
affected_files are unclear
layer_role is unclear
risk_level is missing
```

Result: stop immediately until the missing evidence is provided.

### ESCALATE

The request requires a human decision, layer switch, or separate project gate.

Examples:

```text
task belongs to another layer_role
rollback impact is unclear
downstream references may exist
N1-N6 runtime semantics may be affected
```

Result: stop and hand off to the correct owner or gate.

## 4. Hard Enforcement Rules

```text
No Kernel -> REJECT
No ACCEPT -> STOP
Cross-layer violation -> REJECT
Runtime execution -> REJECT
Runtime execution with one exact passed named policy -> ACCEPT
```

Detailed rules:

1. If `kernel_output` is missing, the Gate returns `REJECT`.
2. If `kernel_output.evidence.kernel_evaluated` is not true, the Gate returns `REJECT`.
3. If `kernel_decision.state` is not `ACCEPT`, the Gate returns `REJECT` or `BLOCK` according to the Kernel reason, and execution must stop.
4. If `cross_layer_violation_detected` is true, the Gate returns `REJECT`.
5. If `runtime_execution_requested` is true, the Gate returns `REJECT` unless all
   of the following are true:
   - `kernel_decision.state == ACCEPT`;
   - `kernel_decision.policy_id` equals
     `n6_strategy_center_display_only_bounded_run_once_v1`,
     `n6_strategy_center_display_only_scheduled_evaluator_v1`, or
     `n6_user_web_immutable_release_bounded_rebind_v1`, or
     `n6_strategy_center_schema_migration_maintenance_window_v1`, or
     `n6_strategy_center_post_081_v2_web_bounded_rebind_v1`, or
     `n6_strategy_center_post_083_v2_web_bounded_rebind_v1`, or
     `n6_strategy_center_post_081_v2_catalog_migration_window_v1`, or
     `n6_strategy_center_post_083_single_user_pending_v2_revision_v1`, or
     `n6_strategy_center_evaluator_quiesce_for_web_rebind_v1`, or
     `n6_strategy_center_pre_canary_web_write_quiesce_v1`, or
     `n6_strategy_center_reviewed_view_date_authority_084_v1`, or
     `n6_strategy_center_post_canary_web_write_restore_v1`, or
     `n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1`, or
     `n6_strategy_center_v1_retirement_after_all_users_v2_v1`, or
     `n6_immutable_release_install_bounded_v1`, or
     `n6_immutable_release_install_pre_rename_validator_recovery_v1`, or
     `n6_immutable_release_install_preflight_git_violation_recovery_v1`, or
     `n4_lifecycle_deactivation_state_columns_controlled_promotion_v1`, or
     `n4_lifecycle_inactive_mark_recovery_v1`, or
     `runtime_hot_cleanup_archive_gated_disk_governance_v1`;
   - `named_policy_evaluated == true`;
   - `named_policy_passed == true`;
   - the complete machine-readable Kernel policy still matches fresh Runtime
     Gate evidence without drift.
6. If the requested action exceeds `affected_files`, the named policy's
   `allowed_write_tables` or `allowed_mutation_resources`, or the declared
   `layer_role`, the Gate returns `REJECT`.
7. For the bounded strategy policy, Runtime Gate must recheck active immutable Release identity, bounded-runner
   presence, current trade date, exact single-user scope, dry-run/watermark/plan
   hash, dedicated ACL, before/after scope, CAS, rollback, attempt counts, and
   every forbidden field. If the virtual executor is loaded or running, it must
   also recheck the exact post-083 Gate2 dynamic positive revision/current
   reviewed-N6 `for_trade_date` coexistence mode, zero pre-Gate2
   dry-run/primary/replay attempts, frozen
   label/plist/Release/runner/PGSERVICE/role-ACL/object-boundary hashes,
   Strategy Center table-write/function-execute/code-reference disjointness,
   exact dry-run -> primary -> same-input replay order, zero executor
   operations, and the rule that normal existing `StartInterval=5` PID/runs
   cycling alone is not drift. It must also recheck the exact four-table
   allowlist; complete observation `SELECT FOR UPDATE/INSERT/UPDATE/DELETE`
   scope predicates/columns; 081 grain; watermark/plan-hash/selection-CAS and
   same-hash replay; surface exclusivity; `surface_kind=observation`; change
   dedup; Web function-only and virtual-executor disjointness; observation-
   preserving rollback; and the V2-dependent 081 rollback reject. Kernel
   evidence is not reusable after drift.

8. Strategy Center date authority is the consensus `for_trade_date` of the
   latest complete singleton stock/index/board reviewed N6 display-basis
   batches. `common_trade_calendar` and N1-N5 raw tables are invalid authority;
   membership is as-of only. Missing/ambiguous batches, date disagreement, or
   lineage/watermark drift returns `REJECT`.
9. Bounded canary and scheduled evaluator execution both require Web
   strategy-write `0`. When it is `1`, only
   `n6_strategy_center_pre_canary_web_write_quiesce_v1` may first perform one
   exact-Web flag-only `1 -> 0` rebind on the unchanged d85 Release, with the
   evaluator already absent and virtual executor untouched.
10. Scheduled evaluator activation additionally requires the current-date
   bounded canary, one scope per tick, pending-first/active-round-robin,
   exact five-second configuration and a frozen twelve-tick stability window.
11. Web write restore requires canary PASS, twelve stable ticks, pending zero
    and one exact-Web flag-only `0 -> 1` rebind. Each remaining user then
    requires a separate one-scope CAS transaction; all-users migration rejects.
    V1 retirement is catalog-only and rejects until every active scope is V2,
    pending is zero, seven remaining-user gates and full replay/isolation/
    projection/SSE verification pass.
8. `runtime_control` cannot use either N6 strategy execution policy. It may use
   `n6_user_web_immutable_release_bounded_rebind_v1` for its exact Web Release
   rebind, or `n6_strategy_center_schema_migration_maintenance_window_v1` for
   the exact prepare-081 quiesce window, or
   `n6_strategy_center_post_081_v2_web_bounded_rebind_v1` for the exact
   post-081 V2 Web rebind, or
   `n6_strategy_center_post_083_v2_web_bounded_rebind_v1` for the exact
   post-083/084 legacy-source-to-formal-target Web rebind. None grants N6
   business or migration authority.
9. For the Web rebind policy, Runtime Gate must freshly recheck source and target
   commit/tree/archive/manifest hashes, non-regressing lineage, immutable
   content, affected resources, PID/PPID/argv/cwd, plist SHA/metadata,
   environment, launchd ownership, primary/rollback attempt counts, readiness,
   routes, stability, evaluator/executor absence, and every forbidden field.
10. For the scheduled-evaluator policy, Runtime Gate must freshly recheck the
    current-request authorization, the frozen 20260722 bounded-canary artifact,
    exact current open trade date, immutable Release commit/tree/archive/
    manifest/filesystem hashes, pinned dfb5b04a/995e4803 source-authority and
    exact auto runner/planner blobs, dependency
    lock/runtime-env hashes and planner-derived argv, exact label/plist/
    StartInterval, `PGSERVICE=n6_strategy_worker`, the four-table
    DML allowlist, per-user isolation, complete observation scope/grain/
    surface/dedup/replay evidence, launchd single-instance plus PostgreSQL
    advisory-lock guards, before/readiness/rollback/concurrency evidence,
    Web function-only and virtual-executor observation disjointness,
    observation-preserving exact-label/plist rollback, V2-dependent 081 schema
    rollback rejection, and every forbidden field. Each tick needs a fresh gate.
    A non-open-day tick may return only the declared no-DML no-op; it never
    inherits current-open-day write authority.
11. For the 081 maintenance-window policy, Runtime Gate must freshly recheck
    current-request authorization; exact 081 forward/rollback hashes; immutable
    Release hashes; exact Web/evaluator label, plist, runner, role, ownership,
    and before-state; the Web-only strategy-write-flag delta; state-driven Web
    bootout/bootstrap and evaluator bootout counts; Web routes/stability;
    evaluator PID/job absence; the four-table read-only watermark scope; the
    immutable token fields, hashes, mode, and expiry; virtual-executor
    configuration and object disjointness; and every forbidden field.
    Ordinary five-second PID/runs cycling is not drift. Any virtual-executor
    operation, migration attempt, database write/lock, old-evaluator bootstrap,
    missing/expired token, extra service, repeated attempt, or business/trading
    effect returns `REJECT`.
12. For the post-081 V2 Web rebind policy, Runtime Gate must freshly recheck
    current-request authorization; committed 081 and absent 082/083 evidence;
    exact source/target commit/tree/archive/manifest/filesystem hashes;
    non-regressing V2 Web/API/UI/SSE, observation, direction, trading-minute
    freshness, and 081 compatibility; Web PID/ownership/plist/environment;
    strategy write `0` before, in the target plist, after readiness, and after
    rollback; evaluator job/PID absence; and frozen virtual-executor
    plist/Release/runner/role/ACL/object-boundary hashes plus Strategy Center
    write disjointness. The only mutable service is the Web. Any database or
    migration request, evaluator operation, virtual-executor operation, write
    enable, missing evidence, drift, extra service, repeated primary attempt,
    N1-N5, queue, business, broker, or trading effect returns `REJECT`. Normal
    virtual-executor StartInterval PID/runs cycling alone is not drift.
12A. For the post-083 V2 Web rebind policy, Runtime Gate must freshly recheck
    current-request authorization; committed 081/082/083/084 and frozen
    schema/catalog evidence; the exact legacy source basename
    `20260724_042200__a1dc7350`; its closure to full commit
    `a1dc73503a07055f7bdb9cd29b378d1272642473`, tree, archive, git-ls-tree,
    manifest, filesystem, path/blob/mode, ownership, and immutable attestation;
    proof that it is the current Web Release and is used only once as the exact
    rollback source; one formally named 40-character target whose name matches
    its commit and whose lineage/schema/N6 capabilities do not regress; exact
    Web ownership/plist/environment with strategy write `1` before, target,
    readiness, and rollback; a passed independent evaluator-quiesce artifact
    plus evaluator job/PID absence and zero evaluator operations; and frozen
    exact virtual-executor `StartInterval=5`
    plist/Release/runner/role-ACL/object-boundary evidence, Web/Strategy Center
    write disjointness, and zero executor operations. The only mutable service
    is the Web, with one primary bootout/bootstrap, zero retries, 60-second
    readiness, 30-second stability, and one conditional exact-source rollback.
    Legacy-source reuse/mutation/target use, a short target, database,
    migration, evaluator/executor operation, extra service, repeated attempt,
    N1-N5, queue, business, broker, or trading effects return `REJECT`. Normal
    virtual-executor PID/runs cycling alone is not drift.
13. For the post-081 V2 catalog migration policy, Runtime Gate must freshly
    select exactly one `N6_user` phase. 082 requires committed 081, absent
    082/083, pending count zero, exact immutable/SQL hashes, and an install-only
    constraint/index/function/ACL plan with no function call or row mutation.
    083 requires committed 081/082, absent 083, passed 082 postflight/ACL,
    current open trade date, pending count zero, V2 selection item count zero,
    and unique active V1 coverage. It may only apply the four declared catalog
    transitions. Both phases require strategy write `0`, evaluator job/PID
    absence, frozen write-disjoint virtual-executor evidence, one transaction,
    one forward attempt, zero retry, and no rollback in the same request.
    Combined phases, wrong order, selection/projection/change writes, Web or
    worker operation, business DML, N1-N5, broker, or trading effects return
    `REJECT`.
14. For the post-083 pending-V2-revision policy, Runtime Gate must freshly
    recheck `pre_dml_guard_harness_recovery_v2`, current-request authorization,
    and N6_user scope. Immutable evidence must bind exactly two ordered,
    automatically aborted historical pre-DML harness transactions: SQLSTATE
    `42704` and exact `role "PUBLIC" does not exist`, then SQLSTATE `42601`
    because the psql request-id variable inside dollar-quoted `DO` did not
    expand. Both must have zero official selection-function calls, zero
    revision/item DML, zero commits, no persisted request id, zero mutation
    attempts, and equality of every declared before/after hash. The ACL guard
    repair must be audit-only
    `pg_catalog.aclexplode(COALESCE(proacl,
    pg_catalog.acldefault('f', proowner))).grantee=0`, the official selection
    function must remain unchanged, and an independent `READ ONLY` preflight
    transaction must complete every complex validation. The later request must
    use a new request id passed through shell/driver parameter binding; only
    its hash may be audited and no token/secret may be logged. The Gate must
    then recheck frozen
    1/1/15/5 ->
    revision_no 6/current 20260723/package_1 v1->v2 values; committed
    081/082/083 postflight hashes; active V2 catalog; strategy write `0`;
    evaluator job/PID absence; frozen, unoperated virtual executor; zero
    pending and V2 items; unique active V1 and previous-revision CAS;
    owner/user-isolated official function; request-id idempotence; one new
    transaction, at most one mutation attempt and zero retry; pending/pending
    output; unchanged other users and projection/change; and zero
    business/trading effects. The mutation transaction permits only
    BEGIN/SET/advisory-lock SELECT/one official function SELECT/read-only
    postflight SELECT/COMMIT and forbids `DO`, psql variable interpolation,
    dynamic SQL, and complex validation. Any historical function call,
    DML/commit, persisted/same request id, mutation attempt, hash mismatch,
    changed failure order/reason, third error kind, third harness transaction,
    official-function change, secret leakage, second mutation attempt, Web
    PUT/write enable, activation, compensation call, multi-scope, package-key
    change, extra table, or missing/drifted evidence returns `REJECT`.
15. For the evaluator-quiesce-for-Web-rebind policy, Runtime Gate must freshly
    recheck current-request authorization, `layer_role=runtime_control`,
    post-083 state, strategy write `1`, exact evaluator label/plist/path,
    immutable Release, runner, role/ACL, launchd ownership, and before state.
    It permits exactly one bootout of that label and requires state-driven proof
    that both PID and job are absent. Evaluator bootstrap, execution, kickstart,
    kill/signal, retry, or automatic restore returns `REJECT`. Web and virtual
    executor must remain unoperated; the latter's label/plist/Release/runner/
    role-ACL/object-boundary hashes and write-disjointness remain frozen.
    Normal configured virtual-executor PID/runs cycling alone is not drift.
    Any database connection, migration, selection/projection/change, queue,
    N1-N5, business, broker, or trading effect returns `REJECT`.
16. General N6 execute, general `runtime_control` service operations, and every
    other runtime/database-write request continue to return `REJECT`.

## 5. Execution Contract

```text
kernel_decision == ACCEPT AND gate_decision == ACCEPT -> allow execution
```

All other combinations stop immediately:

```text
kernel_decision != ACCEPT -> STOP
gate_decision != ACCEPT -> STOP
missing kernel_output -> REJECT
missing gate decision -> STOP
```

Allowed execution means only the approved named action may proceed. The N6
strategy policy authorizes only one bounded display-only primary commit and at
most one exact idempotence replay against its four N6 strategy tables; it never
authorizes LaunchAgent or rollback execution. Its post-083 coexistence branch
only tolerates an already-scheduled, frozen, write/execute/code-disjoint virtual
executor and never authorizes operating it. The Web rebind policy authorizes
only the exact N6 Web plist/label mutation, one primary bootout/bootstrap, and a
conditional one-pair restore of the frozen source Release. The scheduled policy
authorizes only the absent exact label/plist, one install/bootstrap, the exact
immutable scheduled run-once runner at `StartInterval=5`, its four-table DML on
the current open trade date, and one readiness-failure rollback to the frozen
absent state. The post-081 catalog migration policy authorizes exactly one 082
tooling transaction or, only after its postflight, one 083 catalog transition
transaction in separate `N6_user` requests. No policy authorizes a general runtime command, another service,
mutable or immutable Release content change, general business worker, evaluator
under the Web policy, virtual executor, outbox/inbox/checkpoint mutation, N1-N5
behavior change, account/cash/position mutation, proposal/order/trade, real
broker, voice, mobile, sim, or real trading.

### Named policy: n6_strategy_center_evaluator_quiesce_for_web_rebind_v1

Runtime Gate accepts only one explicitly authorized post-083
`runtime_control` bootout of exact label
`com.ashare-v3.n6.strategy-center-evaluator-v1` while strategy write remains
`1`. It requires frozen plist/path/runner/Release/role/ACL/ownership/state,
state-driven PID/job absence, zero bootstrap/kickstart/kill/retry/automatic
restore, and unchanged Web and virtual executor. It grants no database,
migration, evaluator execution, business, trading, or N1-N5 authority.

### Named policy: n6_strategy_center_pre_canary_web_write_quiesce_v1

Runtime Gate accepts only one explicitly authorized `runtime_control` rebind of
`com.ashare-v3.n6.user-web` that preserves the exact d85 Release and changes
only `ASHARE_V3_N6_STRATEGY_CENTER_WRITE_ENABLED=1→0`. The evaluator must
already have no job or runner process; this policy performs zero evaluator and
virtual-executor operations. It allows one primary bootout/bootstrap and, only
after real health failure, one frozen-plist rollback to flag `1`. Any Release,
path, other environment, database, migration, canary, N1-N5, or trading action
returns `REJECT`.

### Named policies: Strategy Center 30-day isolation decommission

The lifecycle retirement override is evaluated before every named-policy
contract. Any retired Strategy Center policy id returns `REJECT`, even when its
historical policy block would otherwise have returned `ACCEPT`.

`n6_strategy_center_decommission_web_runtime_v1` may return `ACCEPT` only for
the exact Web service, one immutable Strategy Center-removal Release, write
flag `0` before/after/rollback, evaluator job/PID absent with zero restore,
one primary bootout/bootstrap, bounded readiness/stability, conditional frozen
source rollback, and optional post-stability read-only evaluator artifact
archive. Any database, virtual-executor, other-service, heartbeat, N1-N5, or
trading operation returns `REJECT`.

`n6_strategy_center_decommission_schema_archive_v1` may return `ACCEPT` only
for one independent `N6_user` transaction over the exact six core tables and
their owned sequences/indexes, a new owner-only archive schema, revoked archive
`USAGE` for the frozen Web role, `n6_strategy_worker`, and `PUBLIC`, exact
Strategy Center-only trigger/function removal, complete per-table evidence,
and a hash-bound rollback valid during the 30-day retention period. Any data or
table drop, truncate, row DML, retry, protected-object change, combined Web
gate, automatic deletion, or heartbeat operation returns `REJECT`.

The 30-day deadline never authorizes physical deletion. Deletion requires a new
independent explicit policy and request after the retention period.

## 6. Golden Rule

### Named policy: n6_immutable_release_install_bounded_v1

Runtime Gate may accept only artifact installation of one already-attested N6
immutable Release. It permits a unique same-parent staging path, validation,
one atomic rename, and attestation writes. For a frozen owner-controlled
Release root at `0555`, it also permits exactly one temporary owner-write
transition to `0755` and requires exactly one restoration to `0555` before
finalization or failure return. Owner/group/ACL/xattr drift, group/other write,
an extra mode transition, or a writable final root returns `REJECT`. It does not permit LaunchAgent or
service operations, database access, evaluator/executor operations, migration,
business or trading writes. Existing Releases must remain unchanged; cleanup
may remove only paths created by the failed attempt. General runtime and
database operations remain `REJECT`.

Gate is mandatory and non-bypassable.

### Named policy: n6_immutable_release_install_pre_rename_validator_recovery_v1

Runtime Gate may accept only one separately authorized recovery for the exact
`aa6d19c169df3837b3115d975587686cc726b87b` pre-rename failure bound to
BLOCKED attestation SHA-256
`9594308305ff68a217d51f6071ded07e4c01892a3ed91227abea9f1586b2edf1`.
Fresh evidence must prove `failure_type=validation_tool_capability_missing`,
zero prior rename/fallback/retry/cleanup attempts, absent target, restored
`0555` Release root, unchanged source hashes, unchanged existing Releases and
the exact preserved staging-v1 path/device/inode/owner/mode/count/ACL/xattr
fingerprints. Staging-v1 is permanent evidence only and may not be reused,
modified, renamed, deleted or cleaned.

The one later recovery request must first create and seal the exact new
validator artifact directories, capability attestation and SHA sidecar
required by the Kernel policy, bind the validator executable and protocol
hashes, and prove complete read-only xattr name/value capability. The
sidecar-recorded attestation SHA, literal `/usr/bin/xattr` SHA and
attestation-embedded executable/protocol hashes must match and be frozen
before Release-root mutation. Capability failure must STOP before Release-root
chmod or staging-v2 creation, but must first confirm root remains `0555` and
FINALIZE the exact sealed recovery failure artifacts. Only after capability PASS may recovery create
the exact fresh same-parent staging-v2, rematerialize it from the frozen
archive, validate every blob/path/mode/ACL/xattr name and value against the
exact release-content-manifest-derived 6288-record
path/name/raw-value/canonical-fingerprint authority and exact owner/group.
Promotion must use one same-root-dirfd
`renameatx_np(RENAME_EXCL|RENAME_NOFOLLOW_ANY|RENAME_RESOLVE_BENEATH)` call;
ordinary or overwrite-capable rename is rejected. Recovery may use one owner-only Release-root
`0555 -> 0755 -> 0555` window. The root must be restored to `0555` immediately
after the rename attempt and before target postflight or attestation writes. A
failure after staging-v2 creation must
recursively seal every created entry to `0444/0555`, attest its identity and
metadata, and restore the root before returning if rename has not succeeded;
writable failure residue is `REJECT`. A post-rename postflight failure must
leave the target immutable and preserve it as evidence without modification
or deletion. Capability drift, partial validation, old
staging reuse/modification/rename/deletion/cleanup, second recovery, fallback
to another install policy, runtime/service/LaunchAgent/port/Git/test/database/
evaluator/executor/migration/N1-N6/business/trading work all return `REJECT`.
Recovery validation, install attestation and sidecar must use the exact absent
new paths/modes/counts in Kernel; unknown request keys, output overwrite or an
unbound write returns `REJECT`. Their directories must not be created until
the Release root is restored or confirmed unchanged at `0555` and the selected
recovery outcome branch, including capability failure, has completed sealing
and postflight; early output
creation returns `REJECT`. After any output path is first created, a
directory/file write or seal failure must seal every created output path to
`0444/0555`, record partial identity/hash evidence and return with zero
writable output residue.
Read-only verification of the frozen staging-v1 remains mandatory. The
governance definition gate cannot execute this policy.

### Named policy: n6_immutable_release_install_preflight_git_violation_recovery_v1

Runtime Gate may accept only the frozen pre-mutation procedural failure caused
by one forbidden read-only Git preflight in the prior validator-recovery
attempt. It requires exact session segment/prefix hashes and tool-call
identities, direct proof that Git was limited to `rev-parse`/`diff`/`show`,
zero Git/worktree mutation and zero filesystem/runtime mutation. The later
execution gate permits no Git and no tests; governance is verified only from
independently frozen current `AGENTS.md` and policy-block raw-byte hashes plus
direct filesystem evidence.

Only capability PASS may open one root `0555 -> 0755 -> 0555` window, create
the exact fresh staging-v2, complete blob/path/mode/owner/ACL/xattr raw-value
validation and attempt one exclusive same-dirfd `renameatx_np`. Staging-v1
remains evidence-only. Prior-policy reuse, fallback, retry, another recovery,
cleanup, service/LaunchAgent/rebind, database/runtime/migration/evaluator/
executor/N1-N6/trading activity, Git or tests are `REJECT`. This governance
definition request cannot execute it.

### Named policy: n4_lifecycle_deactivation_state_columns_controlled_promotion_v1

Runtime Gate treats `6d1b7a24f2f6d6fa6ef5a4d675995c943703101e`
and `a1ff8b0e0dbda579dd2cece1c5b84a10879293bc` only as fixed source
evidence. Their eight-path allowlist, endpoint blobs, combined/rollback patch
hashes and two exact label/original-plist path/SHA bindings cannot change.
They are never accepted as the final execution targets.

Before any bootout, an independent execution request must freeze the exact
policy-definition commit plus two final promotion commits and one final
rollback prepared from that commit. Runtime Gate recomputes that the policy
commit is current Active HEAD with parent `8229124a`, the first promotion is
its direct child, final tip is the first promotion's direct child, rollback is
the final tip's direct child, and rollback tree equals the policy commit tree.
It also recomputes the fixed combined/rollback patch hashes, exact eight-path
set and equality of all eight final blobs to the source endpoint.

Only tracked/index clean state, unchanged original plists, idle workers and
idle children allow one bootout for each exact label, state-driven job/PID/
child absence, one `git merge --ff-only` to the frozen final tip and one
bootstrap from each original plist. Any other label/path/blob/patch/plist,
busy child, fixed sleep, non-ff merge, kickstart, manual execute, retry, push,
checkout/rebase/cherry-pick, automatic rollback, DB DML, message/queue,
historical-event, N2/N3/N5/N6 or trading operation is `REJECT`. Failure may
only report the frozen rollback target; rollback execution remains `REJECT`.
This governance definition request cannot execute the policy.

### Named policy: n4_lifecycle_inactive_mark_recovery_v1

Runtime Gate accepts only one of three separately authorized phases in the
exact post-policy chain: `rollback_restore`, `corrected_promotion`, or
`corrected_code_only_rollback`. The frozen `cadbe91c` commit is content
evidence, not an execution target. Before bootout, the gate freezes every
direct-parent edge and verifies that rollback restore changes only the eight
N4 files to the stable blobs; corrected promotion changes only those files;
and its direct-child code rollback restores the rollback-restore N4 tree.

The corrected inactive contract is current `trigger_mark_candidate=normal`,
prior evidence in `previous_trigger_mark_candidate`, and projection
`false/none`. Schema, constraints and event structure are immutable. Each
phase permits only the two exact labels, one bootout each, state-driven
absence, one ff-only merge and one original-plist bootstrap each. Combining
phases, automatic continuation/rollback, retry, kickstart, manual execute,
DB/message/history or N2/N3/N5/N6 work is `REJECT`. The governance-definition
request cannot execute the policy.

The current revision accepts only after the prior rollback-restore attempt is
hash-bound as a Git metadata permission failure before any repository or
business mutation and both original plists are restored. The prior execution
chain is non-executable evidence. A fresh post-revision chain must reproduce
the four frozen patch hashes, and escalated Git metadata write authority must
be verified before any new bootout. Reusing the prior target, probing merge
without authority, concealing the prior attempt, or executing this definition
request is `REJECT`.

### Named policy: n6_immutable_release_install_eacces_retry_v1

Runtime Gate may accept one fresh artifact-only retry only after one verified
initial `EACCES` rename failure whose target was absent, whose prior staging
remains unchanged and whose Release root was restored to `0555`. It permits a
new staging and target only. After all content checks, the new staging root
may be owner-writable only for the one atomic rename and must end as the new
target at `0555`; the Release root separately must end at `0555`. It never
permits reuse or mutation of the prior staging, a second retry, LaunchAgent,
service, database, evaluator/executor, migration, business or trading work.
General runtime and database operations remain `REJECT`.

### Named policy: n6_immutable_release_install_host_eacces_remediation_v1

Runtime Gate accepts only one artifact-only remediation after a readable,
hash-bound host-level `EACCES` trace. The trace must prove the source staging
was `0555` and that moves to both the same parent and `/tmp` failed. It never
permits mutation/reuse of the orphaned staging, another remediation, service,
LaunchAgent, database, evaluator/executor, migration, business or trading work.

### Named policy: n6_immutable_release_privileged_atomic_install_v1

Runtime Gate accepts only one separately authorized, SHA- and signature-bound
privileged helper invocation. It must atomically promote one verified direct
child staging directory to one absent direct child target via parent-dirfd
`renameatx_np` with `RENAME_EXCL`, `RENAME_NOFOLLOW_ANY` and
`RENAME_RESOLVE_BENEATH`. Unsupported flags, arbitrary paths, shell/copy/
delete/overwrite/chmod/xattr/ACL, services, database, evaluator/executor and
all business or trading paths remain `REJECT`.

### Named policy: n6_immutable_release_privileged_materialize_and_install_v1

Runtime Gate accepts only one separately authorized, SHA/signature-attested
root-only V2 invocation for the frozen
`d85df6328bde223e912dabc3bd65e16df984aa45` archive and manifest. Exact
archive/manifest paths and hashes, source tree, filesystem validation SHA,
6240-file/45-directory counts, and helper attestation must match the
machine-readable Kernel policy. V2 may create one new direct-child staging,
accept only strictly framed PAX `g`/`x` records with `comment`/`path` keys,
seal verified `0644`/`0664`/`0755`/`0775` file and `0755`/`0775` directory
inputs to `0444`/`0555`, reject unsafe tar entries, and atomically promote it
once with exclusive/no-follow/beneath flags. Old staging, all existing Releases, any
other source/hash/count, shell/path escape, metadata mutation,
service/database/evaluator and business/trading paths remain `REJECT`.

### Named policy: n6_immutable_release_privileged_materialize_and_install_f67_v1

Runtime Gate accepts only one separately authorized invocation of the dedicated
SHA/signature-attested f67 helper at
`/usr/local/libexec/ashare-v3/n6-immutable-release-materializer-f67`. The
commit, tree, archive, git-ls-tree, manifest, filesystem validation and bundle
hashes must exactly match the Kernel policy, as must 6240 files, 45
directories, one PAX global header and 108 PAX extended headers. The helper
may create one fresh direct-child staging, seal it to `0444/0555`, perform one
exclusive/no-follow/beneath promotion to an absent commit-bound target, and
write one immutable f67 attestation. Old staging, another input/path/hash,
retry, shell/delete/overwrite/xattr/ACL, runtime, database, N1-N6 and trading
operations remain `REJECT`. This definition gate cannot install or invoke it.

### Named policy: runtime_hot_cleanup_archive_gated_disk_governance_v1

Runtime Gate accepts only one phase from the exact Kernel policy and only in a
separately authorized `runtime_control` execution session. It rechecks the
exact cleanup label/plist, Git and process snapshots, Data/MacRaid capacity,
calendar-authoritative retained set, phase evidence path, required true/false
fields, zero retry, and zero cross-layer or business-service operation.

For `archive_verified_local_reclaim`, Runtime Gate additionally requires the
frozen manifest/summary/allowlist/restore-proof SHA values, full schema/count/
byte cross-bindings, `ARCHIVED_VERIFIED`, `RESTORE_PROOF_PASS`, exact regular
non-symlink source/archive roots, no retained or active-lineage overlap,
candidate-path writer absence, and per-entry device/inode/mode/mtime/size/SHA
revalidation. Only exact allowlist `unlink` operations and append-only progress
journaling are permitted. The Gate requires family/date order and a measured
stop as soon as Data free bytes reach 268435456000. Directory inference,
glob/recursive deletion, archive mutation, database deletion, snapshots in
this phase, any business LaunchAgent operation, manual replay, or retry returns
`REJECT`.

For snapshot fallback, completed reclaim below target and exact purgeable
`com.apple.TimeMachine.*.local` identities are mandatory; every
`com.apple.os.update*` identity returns `REJECT`. Restore accepts one exact
bootstrap only after direct-delete arguments/tokens are absent and verified
archive-required configuration is present. The governance-definition session
always returns `REJECT` for execution.

### Named policy: windows_rebuild_w0_bounded_v1

Runtime Gate defaults every general Windows setup request to `REJECT`. It may
return `ACCEPT` only when `policy_id=windows_rebuild_w0_bounded_v1`,
`layer_role=runtime_control`, `named_policy_evaluated=true`,
`named_policy_passed=true`, and the complete machine-readable policy loaded
from `docs/EXECUTION_KERNEL.md` is semantically equal to the W0 policy in
`AGENTS.md`.

The current policy-definition or policy-modification session always returns
`REJECT` for execution. A later independent request must carry explicit
current-request authorization, exactly one allowed phase, exactly one attempt,
zero retry, all required pre-evidence, exact resources and zero values for
every forbidden-attempt counter. Missing Compiler, Kernel or Runtime Gate
authority, missing fields, unknown fields/resources, drift, path conflict,
unproven identity/ACL effective access, combined phases, excess attempts or
any forbidden operation returns `REJECT`.

Gate binds routine native Codex/application acceptance to
`TDX-STOCK\ashare-ops` SID
`S-1-5-21-2072264739-3883739137-88032818-1006`, Medium integrity, non-admin and
working native SSH. It separately binds elevated operator `TDX-STOCK\47894`
SID `S-1-5-21-2072264739-3883739137-88032818-1002` to Administrators. The
identities must differ. Only the elevated SID, only in an independent
`w0_prepare_and_mutate`, may perform the exact installer/Scheduler-disable/
PG18-disable/D-directory/ACL/service/WSL-config admin allowlist. Its D access
must not be evaluated as routine ACL failure. Unknown/swapped/equal SID,
routine admin/non-Medium/SSH failure, identity mutation, or elevated use from
current WSL interop returns `REJECT`.

For `w0_prepare_and_mutate`, Runtime Gate rechecks the dynamically frozen
current exact Scheduler inventory, `postgresql-x64-18`, `Git.Git`,
`PostgreSQL.PostgreSQL.16`, conditional `Python.Python.3.11`, C/D path, service
identity, empty-cluster, loopback-listener, ACL, CPython/TdxW/17709 and evidence
contracts in the Kernel policy. It requires Mac import, Tushare/Mootdx,
N1-N6/NAS/business write, Scheduler creation/enable/delete, legacy uninstall/
delete, recursive delete, overwrite, reset/clean, automatic cleanup/rollback/
retry and prepare-phase shutdown attempts all to remain zero. The phase must
seal evidence, return `RESTART_REQUIRED` and stop before `wsl --shutdown`.

Scheduler acceptance never depends on a historical fixed count. Gate requires
the preflight to freeze every current task whose TaskName or TaskPath belongs
to AshareV3, record prior-count drift as quality evidence, export each exact
definition, and prove every frozen task Disabled after mutation.

If native CPython 3.11 x64 is valid, Python mutation count must be zero. If and
only if read-only preflight proves it missing or damaged, Gate permits one
machine-wide x64 install/repair of official winget `Python.Python.3.11` at
`C:\Program Files\Python311`, after freezing the resolved highest current safe
3.11.x version, official publisher, signer and SHA-256. It then requires an
existing `python.exe`, PE x64, exact 3.11.x, pip and venv-module verification.
Wrong package/path/version, second attempt, Microsoft Store alias, 3.12/3.14,
source/third-party distribution, business venv/project package mutation,
unknown-Python uninstall, retry or cleanup returns `REJECT` with evidence
preserved.

For `wsl_shutdown_native_control`, Runtime Gate additionally requires the
prior sealed `RESTART_REQUIRED` result and complete pre-shutdown evidence. It
allows one native Windows `wsl --shutdown` attempt only, followed by reconnect
proof that WSL explicitly sees C, `/mnt/d` does not exist, `/etc/wsl.conf`
has `[interop] enabled=false` and `appendWindowsPath=false`, and Linux
`ashare-codex` can still access `/mnt/c` code. Native operations use
`ashare-ops` SSH; UAC installation uses only the independent `47894` channel.
It does not authorize W0
host preparation, N1, database business objects/data or any other mutation.
Only complete W0 post-evidence can produce W0 PASS; N1 remains a separate
later `N1_ingestion` task.
