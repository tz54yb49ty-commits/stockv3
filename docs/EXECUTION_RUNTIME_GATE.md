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

  kernel_input:
    intent: string
    layer_role: string
    affected_files:
      - string
    data_flow: string
    risk_level: low | medium | high | critical

  evidence:
    kernel_evaluated: boolean
    cross_layer_violation_detected: boolean
    runtime_execution_requested: boolean
```

No raw user request, inferred task, or unstated assumption may bypass `kernel_output`.

## 3. Decision States

### ACCEPT

The Kernel exists, the Kernel returned `ACCEPT`, no cross-layer violation is
present, and the requested action remains within approved file/resource and
layer boundaries. Runtime execution must be absent unless the Kernel selected
and fully passed a named fail-closed policy authorized by this contract,
including the Strategy Center bounded evaluator, scheduled evaluator, Web
rebind, schema/catalog maintenance, post-083 single/remaining-user migration,
reviewed-view date authority, and post-canary Web write-restore policies.

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
     `n6_strategy_center_display_only_scheduled_evaluator_f464_v1`, or
     `n6_user_web_immutable_release_bounded_rebind_v1`, or
     `n6_strategy_center_schema_migration_maintenance_window_v1`, or
     `n6_strategy_center_post_081_v2_web_bounded_rebind_v1`, or
     `n6_strategy_center_post_081_v2_catalog_migration_window_v1`, or
     `n6_strategy_center_post_083_single_user_pending_v2_revision_v1`, or
     `n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1`, or
     `n6_strategy_center_pre_canary_web_write_quiesce_v1`, or
     `n6_strategy_center_reviewed_view_date_authority_084_v1`, or
     `n6_strategy_center_post_canary_web_write_restore_v1`, or
     `n6_strategy_center_shadow_activation_grant_v1`, or
     `n6_btrack_delivery_l1_web_readonly_v1`, or
     `n6_btrack_delivery_l2_n6_business_v1`, or
     `n6_btrack_delivery_l3_virtual_runtime_v1`;
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
   also recheck the exact post-083 Gate2/revision-20/current-20260723
   coexistence mode, zero pre-Gate2 dry-run/primary/replay attempts, frozen
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
10. F464 scheduled evaluator activation additionally requires the 20260727
   natural-input canary for exact principal 12/principal-type human_user/user
   11/revision 22/revision-no 1/package_1 v2 with every CAS match and fresh
   business zero increment; `user`, `admin` and unknown principal types are
   rejected for this revision 22 scope; exact F464 commit/tree, blobs, Temporal
   Confluence V2 and 081/082/083 lineage; frozen Web/Evaluator plist,
   offline-manifest and 78-event activation-chain hashes; one scope per tick;
   pending-first/active-round-robin; exact five-second configuration; and a
   frozen twelve-tick stability window.
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
   post-081 V2 Web rebind. None grants N6 business or migration authority.
9. For the Web rebind policy, Runtime Gate must freshly recheck source and target
   commit/tree/archive/manifest hashes, non-regressing lineage, immutable
   content, affected resources, PID/PPID/argv/cwd, plist SHA/metadata,
   environment, launchd ownership, primary/rollback attempt counts, readiness,
   routes, stability, evaluator/executor absence, and every forbidden field.
10. For the F464 scheduled-evaluator policy, Runtime Gate must freshly recheck
    current-request authorization, the exact 20260727 natural-input single-scope
    canary and CAS result, fresh business zero increment, exact current open
    trade date, immutable F464 Release commit/tree/archive/manifest/filesystem
    hashes, exact auto runner/planner/worker blobs, Temporal Confluence V2
    candidate/canonical/bundle lineage, committed 081/082/083 live predicate,
    exact Web target plist, Evaluator source/target plists, offline activation
    manifest and 78-event activation chain, dependency
    lock/runtime-env hashes and planner-derived argv, exact label/plist/
    StartInterval, `PGSERVICE=n6_strategy_worker`, the four-table
    DML allowlist, per-user isolation, complete observation scope/grain/
    surface/dedup/replay evidence, launchd single-instance plus PostgreSQL
    advisory-lock guards, before/readiness/rollback/concurrency evidence,
    Web function-only and virtual-executor observation disjointness,
    observation-preserving exact-label/plist rollback, V2-dependent 081 schema
    rollback rejection, and every forbidden field. Each tick needs a fresh gate.
    A non-open-day tick may return only the declared no-DML no-op; it never
    inherits current-open-day write authority. The absent-label primary path
    allows one atomic plist replacement and one bootstrap, zero bootout/
    kickstart/start/retry, and a settled-absence barrier. Failure compensation
    may restore the exact frozen source plist once but must leave the source
    label/process absent, never bootstrap 658, and never restore an empty state.
11. For `n6_strategy_center_shadow_activation_grant_v1`, Runtime Gate accepts
    only a later independent `runtime_control` request carrying parent approval
    `N6_AI_SIMULATED_INVESTOR_RESUMABLE_ACTIVATION`. It must freshly verify the
    second-level immutable supersession manifest and complete SHA chain, the external
    attestation of the final governance commit, the manifest-bound Web and
    Evaluator live commit/tree/plist anchors, both source-to-target ancestry
    paths, critical N6 blob/API/strategy non-regression, and unchanged Virtual
    Executor, N1-N5, broker, and trading boundaries.
12. The same policy requires `GOVERNANCE=passed`,
    `EVALUATOR_RESUME_FIX=passed`, an evidence-bound resume of the failed
    `BOUNDED_REBIND`, `BOUNDED_REBIND_WEB_TARGET=planned`, and
    `BOUNDED_REBIND_EVALUATOR_TARGET=blocked_pending_canary`, plus an unexpired
    WEB_TARGET lease. Ordinary checkpoint JSON is evidence only.
13. WEB_TARGET may install immutable f464 and rebind only exact Web from d85 to
    f464. Strategy-write remains `0`; the Evaluator job/runner must remain
    absent/0. Any Evaluator operation, canary, kickstart, runner, database,
    Virtual Executor, N1-N5, broker/trading access, extra label, or empty-state
    restore returns `REJECT`.
14. EVALUATOR_TARGET cannot become planned or receive a lease until WEB_TARGET
    is passed and a later independent current-date bounded canary PASS is
    imported into the hash chain. It may then bootstrap only the exact
    Evaluator label to the same f464 target.
15. Candidate, strategy-rule, implementation, target-artifact,
    ancestry, critical-blob, API, or boundary drift is semantic drift and
    terminates the parent approval. Only a freshly attested compatible
    source-runtime-anchor change is operational drift eligible for immutable
    supersession. The d85 bundle is historical; the only current target bundle
    is f464 file `6efda630...` with internal SHA `119296de...`. No existing
    manifest may be rewritten.
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
15. For remaining post-083 users, Runtime Gate may ACCEPT only one explicitly
    authorized principal/user scope whose active V1 predecessor, current N6
    authority date, same package-key set and predecessor+1 CAS are frozen.
    Strategy write must remain `1`; Web PUT is forbidden. A running evaluator
    may be observed but must not be operated. The target owner-isolated
    selection function must be independently attested; the existing session-
    token Web function and hand-written SQL are not substitutes. Missing
    owner-function proof returns
    `scope_expansion_required=owner_selection_function` and `REJECT`.
    Exactly one transaction, one advisory lock, one official function call, one
    mutation attempt and zero retry may insert only the pending revision/items.
    Activation, projection/change, catalog/schema, executor, business,
    trading, N1-N5, all-users, multi-scope, date/hash drift or a second attempt
    returns `REJECT`.
16. General N6 execute, general `runtime_control` service operations, and every
    other runtime/database-write request continue to return `REJECT`.
17. The three `n6_btrack_delivery_*_v1` policy ids are one reusable policy
    family. A request must match exactly one lane from
    `N6_B_TRACK_DELIVERY_GOVERNANCE_V1`; ambiguous or mixed-lane requests
    return `BLOCK`, and a request for a new one-off N6 delivery policy returns
    `REJECT`.
18. L1 accepts only a separate, explicitly authorized Web-only immutable
    Release rebind after an isolated implementation/test gate. Database,
    migration, quote writer, executor, stop-loss and
    proposal/order/trade/cash/position/lot effects must all be zero.
18a. The reusable L1 `post_decommission_web_readonly_rebind` deployment phase
    accepts only a prior L1 `ACCEPT` for a Web/read-only, UX-only,
    non-Strategy, non-regressing candidate. Live/source/target/readiness/
    rollback strategy-write must stay `0`; the exact Strategy evaluator must
    remain absent with zero operations. The virtual executor may remain loaded
    and naturally rotate PID/runs, but must stay label/plist/Release/runner/
    role/ACL/ownership/object/hash disjoint from Web with zero operations.
    Exact source evidence mode, target Release-specific immutable manifest,
    lineage and exact Web-only diff;
    retired `307` notice redirect and all three exact `410`/`no-store` APIs;
    WorkingDirectory/PYTHONPATH-only Release binding delta; exactly two byte-
    identical ProgramArguments using literal `python3` or a frozen absolute
    immutable non-Release-bound system interpreter plus the fixed relative
    script. Absolute-interpreter evidence must freeze the `/Library` trusted
    path chain, each in-boundary symlink hop/readlink, resolved canonical regular
    target, owner/group/mode/flags/ACL/SHA, no escape/cycle/ambiguity, exact
    source/target identity, zero replacement, and effective non-writability by
    the frozen Web service principal. Target script containment/type/symlink/
    write-bit/owner/mode/hash/manifest evidence is mandatory. A pre-manifest
    legacy source may use
    read-only reconstructed exact commit/tree/exclusions, complete present-file
    blob/mode, no-extra, sealed and deterministic object-hash evidence only for
    source/rollback; it cannot be modified or replace target manifest. The
    primary budget is one safe plist
    replace/swap, one bootout, wait `>=1s` plus old job/PID absence, and one
    bootstrap. Kickstart/retry/downgrade/second primary are forbidden; primary
    failure alone permits one frozen-source rollback. Missing evidence or any
    runner/manifest/reconstruction/route/plist/side-effect/operation-count drift
    returns `REJECT`.
19. L2 normally accepts separate N6-user migration and runtime-control Web rebind
    phases. The full migration filename is the identity, forward/rollback and
    PG16 evidence are mandatory, and automatic proposal, virtual-money or
    worker effects return `REJECT`.
    The sole bounded-consumer addition is
    `phase_id=trigger_status_projection_20260731_backfill`. Runtime Gate must
    freshly require the exact L2 machine object, independent current-request
    N6-user authorization, frozen date/run/runner/limit/input census and outbox
    range, a zero-persistence full-batch simulation, and an exact-run rollback
    artifact already verified statically and on PG16. It permits one transaction
    and one execute attempt, with writes only to `n6_trigger_status_current` and
    this consumer's exact inbox/checkpoint state; `common_event_outbox` is
    SELECT-only and status updates are zero. Any 089 table-drop rollback,
    protected-consumer or old-checkpoint change, `trigger_pct` status surface,
    `ActionEligible` payload mutation, retry, manual SQL, migration, Release,
    service, N1-N5, trade, virtual-executor, Strategy Center, or bundled next
    phase returns `REJECT`. A `runtime_control` governance session cannot use
    this phase.
20. L3 accepts only N6 virtual-account work with current-request authorization,
    a unified immutable Release, bounded smoke, governed confirmed queue,
    two-stage human confirmation, current open date/session, two-minute
    `passed/ok` identity-matched quote, principal/account/scope, cash/budget/
    board-lot/natural-day-T+1 checks, independent role, full audit and a frozen
    bootout command. Real broker/order, automatic proposal creation or
    confirmation, N6 writeback to N1-N5, or missing evidence returns `REJECT`.
21. Historical named policies remain append-only compatibility evidence.
    Their existence does not authorize cloning another per-migration or
    per-release policy for a normal new N6 request.

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

Allowed execution means only the approved action may proceed. It does not authorize runtime commands, database writes, rollback, worker startup, outbox consumption, N1-N6 behavior changes, voice, mobile, sim, position, or real trading.

## 6. Golden Rule

Gate is mandatory and non-bypassable.
