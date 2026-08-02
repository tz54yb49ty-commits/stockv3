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
    data_flow: string
    risk_level: low | medium | high | critical

  kernel_decision:
    state: ACCEPT | REJECT | BLOCK | ESCALATE
    reason: string

  gate_decision:
    state: ACCEPT | REJECT | BLOCK | ESCALATE
    reason: string

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
6. A runtime `ACCEPT` must record the exact `policy_id`, `affected_resources`,
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
   `n6_strategy_center_post_081_v2_catalog_migration_window_v1`, and
   `n6_strategy_center_post_083_single_user_pending_v2_revision_v1`, and
   `n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1`, and
   `n6_strategy_center_pre_canary_web_write_quiesce_v1`, and
   `n6_strategy_center_shadow_activation_grant_v1`, and
   `n6_btrack_delivery_l1_web_readonly_v1`, and
   `n6_btrack_delivery_l2_n6_business_v1`, and
   `n6_btrack_delivery_l3_virtual_runtime_v1`; any other
   runtime policy id must trace `REJECT` and `STOP`.
8. A Web bounded-rebind `ACCEPT` must additionally record the exact label/plist,
   source and target Release identities and hashes, lineage verdict, frozen
   PID/PPID/argv/cwd/plist/environment/ownership evidence, primary and rollback
   attempt counts, readiness/route/stability timestamps, whether rollback was
   triggered, and proof that evaluator/executor and all forbidden effects stayed
   absent.
8a. An N6 B-track delivery trace must record the four normalized user brief
    fields, exactly one L1/L2/L3 policy id, canonical integration commit/tree,
    baseline-registry version, exact affected services/tables, gate phase,
    rollback/bootout evidence required by that lane, and a forbidden-effect
    zero summary. Mixed lanes or a new one-off policy request must trace
    `BLOCK`/`REJECT` before runtime.
8b. An L1 `post_decommission_web_readonly_rebind` trace must additionally bind
    the prior L1 `ACCEPT`, Web-only UX-only non-Strategy exact diff, immutable
    source evidence mode and source commit/tree/fileset/exclusion/object hashes;
    mandatory target Release-specific immutable commit/tree/archive/fileset/
    per-entry mode-owner-SHA/exclusion/object manifest and lineage;
    live/source/target/readiness/rollback strategy-write values; exact retired
    `307` and three `410`/`no-store` results; evaluator absence/operation count;
    virtual-executor disjoint hashes, operation count and PID/runs-only rotation
    verdict; exact two-token ProgramArguments, interpreter form and frozen
    evidence, including the full trusted path owner/group/mode/flags/ACL chain,
    each symlink hop/readlink, resolved canonical target/SHA, frozen service
    principal groups, effective-non-writable verdict, zero replacement and
    exact source/target-chain identity; relative-script token,
    WorkingDirectory/PYTHONPATH and target
    script manifest checks; plist before/after hashes; replace/swap, bootout,
    wait, old job/PID
    absence, bootstrap, kickstart/retry/downgrade counts; rollback trigger/count;
    and DB/N1-N5/evaluator/executor/business/proposal/cash/position/trade zeroes.
    Missing fields or any mismatch must trace `REJECT`/`STOP`; the trace must
    retain the existing L1 policy id and must not name or revive a historical
    one-off policy.
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

14. A remaining-users pending-V2 `ACCEPT` must record exactly one supplied
    principal/user scope, current N6 authority `for_trade_date`, active-V1
    predecessor and predecessor+1 CAS, unchanged package keys, and the
    independently attested immutable owner-isolated selection function. It
    must record strategy write `1`, no Web PUT, evaluator observation without
    operation, one transaction, one advisory lock, one official function call,
    one mutation attempt, zero retry, pending/pending postflight, unchanged
    other users and projection/change watermarks, and zero forbidden effects.
    Missing owner-function proof is `scope_expansion_required=owner_selection_function`
    and `REJECT`; the session-token Web function and manual SQL are never valid
    substitutes. Any all-users/multi-scope request, date/hash/predecessor/key
    drift, activation, extra table, evaluator/executor operation, retry,
    business/trading, or N1-N5 effect must trace `REJECT` and `STOP`.

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

No execution without a complete trace entry.

Date-authority traces must record the three reviewed display-view batch
identities (`for_trade_date`, `source_trade_date`, `source_run_id`, row count),
projection/card watermarks and membership as-of provenance. They must not use a
`common_trade_calendar` or N1-N5 raw-table authority. Post-canary write-restore
traces additionally record flag `0 -> 1`, canary result, 12 evaluator ticks,
pending count, exact Web plist/Release hashes and the single rebind budget.

Second-level resumable-rebind traces must retain the original failed
BOUNDED_REBIND event/evidence, the full three-SHA supersession chain,
`72b1d50` control-plane commit/tree, d85/ee2b/write-0 source, f464 target and
bundle upgrade hashes. WEB_TARGET traces record immutable installation and the
exact Web-only rebind while proving Evaluator job absent/runner 0 and zero
Evaluator operations. EVALUATOR_TARGET must trace
`blocked_pending_canary` until WEB_TARGET passed and a separate current-date
bounded-canary PASS is appended; pre-canary planning, lease, or bootstrap must
trace `REJECT`.

Pre-canary write-quiesce traces remain historical Gate3+ authority and record
the exact flag-only `1 -> 0` delta on the unchanged Release plus zero
Evaluator, Virtual Executor, database, canary, N1-N5 and trading operations.
