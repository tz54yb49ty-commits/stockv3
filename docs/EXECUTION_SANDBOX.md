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

Any cross-layer mutation, runtime execution request, database operation, worker
startup, or N1-N6 mutation must produce a simulated STOP outcome by default.
Only a fully matched named Kernel/Runtime-Gate policy may predict `EXECUTE`;
this includes the historical
`n6_strategy_center_pre_canary_web_write_quiesce_v1` and the resumable
`n6_strategy_center_shadow_activation_grant_v1` WEB_TARGET constraints below.
The sandbox itself never performs an action.

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

For `n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1`, the
sandbox may predict `EXECUTE` only for one explicitly supplied principal/user
scope with a current N6 authority date, exact active-V1 predecessor CAS and
unchanged package keys. It requires strategy write `1`, forbids Web PUT and
evaluator operation, and requires independent attestation of an immutable
owner-isolated selection function. Missing attestation predicts
`scope_expansion_required=owner_selection_function` and `STOP`; the existing
session-token Web function and hand-written SQL cannot satisfy it. The only
predicted diff is pending revision/items in the two selection tables, with one
transaction, one attempt and zero retry.

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

### 6.1 N6 B-track Lane Simulation

For `n6_btrack_delivery_l1_web_readonly_v1`, simulation must predict only the
exact Web diff and, when separately authorized, one Web immutable-Release
rebind. Any database, quote-writer, executor, stop-loss, or virtual-account
effect predicts `STOP`.

For `n6_btrack_delivery_l2_n6_business_v1`, implementation, migration,
Release rebind, and acceptance are simulated as separate gates. The simulation
must bind the complete migration filename, rollback, function/ACL contract, and
business-table before/after digest. It must not execute those phases.

For `n6_btrack_delivery_l3_virtual_runtime_v1`, simulation additionally
requires bounded-smoke evidence, confirmed-queue disposition, independent
service role, immutable lineage, complete virtual-account audit, and an
immediate bootout plan. Missing any item predicts `STOP`.

The sandbox must reject requests that mix lanes or ask for a new one-off policy
where one of the three reusable lanes already applies.

## 7. Golden Rule

Sandbox simulation is not execution.

No real change is allowed inside the sandbox.

The sandbox recognizes `n6_strategy_center_reviewed_view_date_authority_084_v1`
only for one reviewed-view consensus 084 forward with frozen source/card
watermarks, strategy write `0`, evaluator quiescence and no calendar/raw-table,
selection, projection, change or trading access. It recognizes
`n6_strategy_center_post_canary_web_write_restore_v1` only for one exact-Web
`0 -> 1` rebind after canary PASS, 12 stable ticks and pending `0`; all other
runtime/database/worker operations remain simulated `STOP`.

The sandbox also recognizes
`n6_strategy_center_post_083_multi_user_pending_v2_revision_v1` only as a
single-scope selection mutation: it predicts STOP unless strategy-write is
`0`, the exact evaluator is absent, 081/082/083 and the current N6 authority
are attested, pending and V2-item counts are zero, the active V1 predecessor
and CAS are frozen, and the sole permitted owner function is called once.
It never performs the database call; all projection/change, upstream, account,
or trading mutations remain STOP.

For `n6_strategy_center_shadow_activation_grant_v1`, sandbox prediction may be
`EXECUTE` only for WEB_TARGET after the failed parent checkpoint is resumed
with frozen failure evidence, the second-level supersession and complete SHA
chain are verified, `GOVERNANCE` and `EVALUATOR_RESUME_FIX` remain passed,
WEB_TARGET is planned, EVALUATOR_TARGET is `blocked_pending_canary`, and the
short WEB_TARGET lease matches the latest checkpoint.

WEB_TARGET simulation contains immutable f464 installation and one exact-Web
d85-to-f464 rebind with strategy-write fixed at `0`. The Evaluator must remain
absent and has zero operations. EVALUATOR_TARGET predicts `STOP` until
WEB_TARGET passed plus a later independent current-date bounded canary PASS;
only then may it be planned for the same f464. Kickstart, runner, same-session
canary, extra labels, Virtual Executor, database, N1-N5, broker/trading writes,
empty restore, or semantic drift always predicts `STOP`.

`n6_strategy_center_pre_canary_web_write_quiesce_v1` remains the Gate3+
flag-only historical path. It predicts `EXECUTE` only for exact Web `1 -> 0`
on the unchanged Release with Evaluator already absent and zero Virtual
Executor/database/canary/N1-N5/trading operations.
