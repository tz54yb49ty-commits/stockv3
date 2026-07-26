# Execution Test Suite

## 1. Purpose

The Execution Test Suite defines documentation-only validation for the A股监控系统 v3 execution-control system.

It validates:

```text
Execution Compiler correctness
Kernel decision correctness
Gate enforcement correctness
Binding correctness
Trace completeness
Sandbox behavior
```

This document defines test intent, scope, expected outcomes, and failure categories only. It introduces no runtime implementation, no test runner, no database behavior, no code execution, and no N1-N6 system change.

## 2. Test Scope

The suite covers the current execution-control documents and the consolidated conceptual architecture:

```text
Execution Compiler -> Compiler Layer
Execution Kernel -> Decision Engine
Runtime Gate -> Decision Engine
Binding Layer -> Decision Engine
Execution Trace -> Execution Runtime
Execution Sandbox -> Execution Runtime
```

Tests must preserve:

```text
determinism
DAG correctness
decision safety
layer boundary enforcement
traceability
sandbox no-write behavior
```

## 3. Test Types

### 3.1 Compiler Tests

Compiler tests validate that natural language tasks compile into a valid `execution_plan` DAG.

Required validations:

```text
DAG must include PLAN -> VALIDATE -> MODIFY -> VERIFY -> FINALIZE.
No cycles allowed.
Every MODIFY must be preceded by VALIDATE.
Every node must declare layer_role.
Every node must stay within affected_files.
No cross-layer node is allowed.
```

Positive cases:

```text
single documentation-only file creation
single documentation-only file update
read-only validation plan with no MODIFY node, if explicitly declared as no-write
```

Negative cases:

```text
missing PLAN node
missing VALIDATE node before MODIFY
MODIFY before VALIDATE
cycle in edges
node with undeclared layer_role
node affecting a file outside affected_files
node attempting N1-N6 runtime operation from runtime_control
```

Expected result:

```text
valid DAG -> compiler_status=passed
invalid DAG -> compiler_status=failed and final_status=STOP
```

### 3.2 Kernel Tests

Kernel tests validate decision-state correctness.

Required validations:

```text
ACCEPT / REJECT / BLOCK / ESCALATE correctness.
Invalid input must NOT produce ACCEPT.
Missing layer_role must produce BLOCK.
Cross-layer mutation must produce REJECT.
Runtime execution request must produce REJECT.
Ambiguous task must stop.
```

Positive cases:

```text
documentation-only task with declared layer_role and affected_files -> ACCEPT
read-only inspection task within current layer_role -> ACCEPT
```

Negative cases:

```text
missing layer_role -> BLOCK
missing affected_files for write task -> BLOCK
request to modify N1 while current layer_role=N3_market_data -> REJECT or ESCALATE
request to execute runtime command -> REJECT
request to write outside approved files -> REJECT
ambiguous request with unclear target -> BLOCK
```

Expected result:

```text
valid input within boundary -> ACCEPT
invalid input -> REJECT / BLOCK / ESCALATE
invalid input must never produce ACCEPT
```

### 3.3 Gate Tests

Gate tests validate final enforcement after Kernel output.

Required validations:

```text
cross-layer violation detection
runtime execution prevention
invalid kernel_output rejection
missing Kernel output rejection
non-ACCEPT Kernel state stops execution
```

Positive cases:

```text
kernel_output present
kernel_decision=ACCEPT
cross_layer_violation_detected=false
runtime_execution_requested=false
affected_files within approved scope
```

Negative cases:

```text
kernel_output missing -> REJECT
kernel_evaluated=false -> REJECT
kernel_decision=REJECT -> STOP
kernel_decision=BLOCK -> STOP
kernel_decision=ESCALATE -> STOP
cross_layer_violation_detected=true -> REJECT
runtime_execution_requested=true -> REJECT
affected_files exceeds approved scope -> REJECT
```

Expected result:

```text
valid kernel_output with ACCEPT and no violations -> gate_status=ACCEPT
invalid kernel_output or violation -> gate_status=REJECT / BLOCK / ESCALATE and final_status=STOP
```

### 3.4 Binding Tests

Binding tests validate that execution-control stages cannot be bypassed or reordered.

Required validations:

```text
Kernel must run before Gate.
Gate must run before execution.
Missing stage -> INVALID.
Out-of-order stage -> INVALID.
Direct file modification without full chain -> INVALID.
```

Positive cases:

```text
Compiler -> Kernel -> Gate -> Binding -> Trace -> Execution
Compiler -> Kernel -> Gate -> Binding -> Trace -> STOP
```

Negative cases:

```text
Kernel missing
Gate missing
Binding missing
Gate before Kernel
Execution before Gate
Execution before Trace
Direct MODIFY without Compiler DAG
Direct MODIFY without VALIDATE
```

Expected result:

```text
ordered full chain -> binding_status=ACCEPT
missing or out-of-order stage -> binding_status=REJECT and final_status=STOP
```

### 3.5 Trace Tests

Trace tests validate audit completeness.

Required validations:

```text
every EXECUTE must be recorded
every STOP must be recorded
every REJECT / BLOCK must include reason
no partial traces allowed
no overwritten history allowed
replay must reconstruct full decision chain
```

Positive cases:

```text
EXECUTE trace includes compiler output, decision state, binding result, final_status, affected_files, layer_role, risk_level
STOP trace includes failure point and reason
ESCALATE trace identifies target layer or gate
```

Negative cases:

```text
missing kernel_input
missing decision state
missing binding_decision
missing final_status
missing affected_files
missing failure reason for REJECT / BLOCK
trace overwritten instead of appended correction
replay cannot reconstruct decision origin
```

Expected result:

```text
complete trace -> trace_status=passed
missing or partial trace -> trace_status=failed and final_status=STOP
```

### 3.6 Sandbox Tests

Sandbox tests validate simulation behavior.

Required validations:

```text
no real file modification
diff preview only
full execution simulation correctness
no runtime execution
no database operations
no worker startup
no N1-N6 state mutation
all outputs are hypothetical
```

Positive cases:

```text
sandbox output includes execution_plan
sandbox output includes simulated kernel_input
sandbox output includes simulated kernel_decision
sandbox output includes simulated gate_decision
sandbox output includes simulated binding_decision
sandbox output includes predicted final_status
sandbox output includes proposed file diffs as read-only preview
```

Negative cases:

```text
sandbox writes a file
sandbox applies a patch
sandbox connects to database
sandbox starts worker
sandbox consumes outbox
sandbox mutates N1-N6 state
sandbox omits diff preview for proposed write
sandbox predicts EXECUTE despite decision failure
```

Expected result:

```text
read-only full simulation -> sandbox_status=passed
real side effect or inconsistent decision chain -> sandbox_status=failed and final_status=STOP
```

## 4. Failure Conditions

Any test failure must be categorized as one of:

```text
structural failure
decision failure
enforcement failure
trace failure
```

### 4.1 Structural Failure

Definition:

```text
DAG invalid, missing required node, invalid edge, cycle detected, or MODIFY lacks prior VALIDATE.
```

Examples:

```text
PLAN -> MODIFY without VALIDATE
cycle: VERIFY -> MODIFY -> VERIFY
missing FINALIZE
node outside affected_files
```

### 4.2 Decision Failure

Definition:

```text
Wrong ACCEPT / REJECT / BLOCK / ESCALATE result for the given input.
```

Examples:

```text
invalid input produces ACCEPT
runtime execution request produces ACCEPT
missing layer_role does not produce BLOCK
cross-layer mutation does not produce REJECT
```

### 4.3 Enforcement Failure

Definition:

```text
Bypass, out-of-order execution, direct modification, or runtime side effect is allowed.
```

Examples:

```text
Gate skipped
Binding skipped
execution occurs before trace
file modification occurs without DAG
database operation occurs in documentation-only mode
```

### 4.4 Trace Failure

Definition:

```text
Audit record is missing, incomplete, overwritten, or not replayable.
```

Examples:

```text
STOP has no reason
REJECT has no decision origin
trace lacks affected_files
history overwritten instead of appended
replay cannot reconstruct Kernel / Gate / Binding or consolidated Decision Engine path
```

## 5. Test Case Schema

Each test case should be expressed as documentation data:

```yaml
test_case:
  id: string
  type: compiler | kernel | gate | binding | trace | sandbox
  purpose: string
  input:
    task: string
    layer_role: string
    affected_files:
      - string
    risk_level: low | medium | high | critical
  expected:
    compiler_status: passed | failed | not_applicable
    decision_state: ACCEPT | REJECT | BLOCK | ESCALATE | not_applicable
    gate_status: ACCEPT | REJECT | BLOCK | ESCALATE | not_applicable
    binding_status: ACCEPT | REJECT | BLOCK | ESCALATE | not_applicable
    trace_status: passed | failed | not_applicable
    sandbox_status: passed | failed | not_applicable
    final_status: EXECUTE | STOP
    failure_category: structural failure | decision failure | enforcement failure | trace failure | none
```

## 6. Required Baseline Tests

### 6.1 Valid Documentation-Only Creation

```yaml
test_case:
  id: "baseline_valid_docs_create"
  type: "sandbox"
  purpose: "Validate a documentation-only file creation path."
  input:
    task: "Create one new docs file."
    layer_role: "runtime_control"
    affected_files:
      - "docs/EXAMPLE.md"
    risk_level: "low"
  expected:
    compiler_status: "passed"
    decision_state: "ACCEPT"
    gate_status: "ACCEPT"
    binding_status: "ACCEPT"
    trace_status: "passed"
    sandbox_status: "passed"
    final_status: "EXECUTE"
    failure_category: "none"
```

### 6.2 Invalid DAG Missing Validate

```yaml
test_case:
  id: "invalid_dag_missing_validate"
  type: "compiler"
  purpose: "Reject MODIFY without prior VALIDATE."
  input:
    task: "Modify a docs file without validation."
    layer_role: "runtime_control"
    affected_files:
      - "docs/EXAMPLE.md"
    risk_level: "low"
  expected:
    compiler_status: "failed"
    decision_state: "not_applicable"
    gate_status: "not_applicable"
    binding_status: "not_applicable"
    trace_status: "passed"
    sandbox_status: "not_applicable"
    final_status: "STOP"
    failure_category: "structural failure"
```

### 6.3 Runtime Execution Rejected

```yaml
test_case:
  id: "runtime_execution_rejected"
  type: "kernel"
  purpose: "Reject runtime execution in documentation-only control path."
  input:
    task: "Run a worker."
    layer_role: "runtime_control"
    affected_files: []
    risk_level: "critical"
  expected:
    compiler_status: "passed"
    decision_state: "REJECT"
    gate_status: "REJECT"
    binding_status: "not_applicable"
    trace_status: "passed"
    sandbox_status: "not_applicable"
    final_status: "STOP"
    failure_category: "decision failure"
```

### 6.4 Gate Bypass Rejected

```yaml
test_case:
  id: "gate_bypass_rejected"
  type: "binding"
  purpose: "Reject execution when Gate is missing."
  input:
    task: "Modify file after Kernel only."
    layer_role: "runtime_control"
    affected_files:
      - "docs/EXAMPLE.md"
    risk_level: "medium"
  expected:
    compiler_status: "passed"
    decision_state: "ACCEPT"
    gate_status: "not_applicable"
    binding_status: "REJECT"
    trace_status: "passed"
    sandbox_status: "not_applicable"
    final_status: "STOP"
    failure_category: "enforcement failure"
```

### 6.5 Missing Trace Stops Execution

```yaml
test_case:
  id: "missing_trace_stops_execution"
  type: "trace"
  purpose: "Reject execution when trace is incomplete."
  input:
    task: "Execute with complete decisions but no trace."
    layer_role: "runtime_control"
    affected_files:
      - "docs/EXAMPLE.md"
    risk_level: "medium"
  expected:
    compiler_status: "passed"
    decision_state: "ACCEPT"
    gate_status: "ACCEPT"
    binding_status: "ACCEPT"
    trace_status: "failed"
    sandbox_status: "not_applicable"
    final_status: "STOP"
    failure_category: "trace failure"
```

### 6.6 Exact N6 Strategy Bounded Policy Accepted

```yaml
test_case:
  id: "n6_strategy_center_display_only_bounded_run_once_accept"
  type: "gate"
  purpose: "Accept only the complete single-user display-only strategy policy."
  input:
    task: "Run one bounded strategy-center primary commit and one exact replay."
    layer_role: "N6_user"
    affected_files: []
    risk_level: "high"
    policy_id: "n6_strategy_center_display_only_bounded_run_once_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: true
  expected:
    compiler_status: "passed"
    decision_state: "ACCEPT"
    gate_status: "ACCEPT"
    binding_status: "ACCEPT"
    trace_status: "passed"
    sandbox_status: "passed"
    final_status: "EXECUTE"
    failure_category: "none"
```

The fixture for this case must satisfy every machine-readable field in
`docs/EXECUTION_KERNEL.md`; the abbreviated YAML above is not authority to omit
scope, Release, dry-run, watermark, plan hash, ACL, CAS, rollback, write-table,
observation scope/grain/surface/dedup/replay, Web function-only, virtual-executor
observation disjointness, V2-dependent 081 rollback rejection, attempt-limit,
or forbidden-field evidence. The post-083 Gate2 positive fixture
must use revision 20, current trade date 20260723, zero pre-Gate2 attempts, and
exact dry-run -> primary -> same-input replay order. It
may coexist with the already-loaded `StartInterval=5` virtual executor only when
the exact label/plist/Release/runner/PGSERVICE/role-ACL/object-boundary hashes
are frozen, Strategy Center table-write/function-execute/code-reference
disjointness is proven, and executor operation attempts are zero. Normal PID or
runs-counter movement alone must remain accepted.

### 6.7 Incomplete or General N6 Runtime Rejected

```yaml
test_case:
  id: "n6_strategy_center_bounded_policy_incomplete_reject"
  type: "gate"
  purpose: "Reject partial policy matches and all general N6 execute requests."
  input:
    task: "Run N6 strategy evaluation without a complete single-user scope."
    layer_role: "N6_user"
    affected_files: []
    risk_level: "high"
    policy_id: "n6_strategy_center_display_only_bounded_run_once_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: false
  expected:
    compiler_status: "failed"
    decision_state: "REJECT"
    gate_status: "REJECT"
    binding_status: "not_applicable"
    trace_status: "passed"
    sandbox_status: "passed"
    final_status: "STOP"
    failure_category: "decision failure"
```

Additional negative fixtures must return `REJECT` for any virtual-executor
bootout/bootstrap/modification/other operation; label/plist/Release/runner/
PGSERVICE/role-ACL/object-boundary drift; Strategy Center selection/catalog/
projection/observation/change write privilege; formal Strategy Center function
`EXECUTE`; code reference to those objects; wrong phase/revision/order; or a
fifth table beyond the exact four-table evaluator allowlist. Negative fixtures
must also cover missing observation predicates/insert columns, non-081 grain,
cross-scope/date writes, same-episode dual surfaces, duplicate changes, wrong
change surface, replay drift, Web/virtual-executor observation table authority,
executor observation code references, observation-deleting rollback, and 081
schema rollback with a V2 dependency.

### 6.8 Exact N6 Web Immutable Release Bounded Rebind Accepted

```yaml
test_case:
  id: "n6_user_web_immutable_release_bounded_rebind_accept"
  type: "gate"
  purpose: "Accept only one exact-label, single-source/single-target, fail-closed Web rebind."
  input:
    task: "Rebind only com.ashare-v3.n6.user-web to one verified immutable Release."
    layer_role: "runtime_control"
    affected_files: []
    risk_level: "critical"
    policy_id: "n6_user_web_immutable_release_bounded_rebind_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: true
  expected:
    compiler_status: "passed"
    decision_state: "ACCEPT"
    gate_status: "ACCEPT"
    binding_status: "ACCEPT"
    trace_status: "passed"
    sandbox_status: "passed"
    final_status: "EXECUTE"
    failure_category: "none"
```

The fixture for this case must satisfy every machine-readable field in
`docs/EXECUTION_KERNEL.md`; the abbreviated YAML above is not authority to omit
exact resource/operation lists, source/target hashes, lineage, ownership,
state-driven teardown, attempt limits, readiness, routes, stability, rollback,
evaluator/executor, or forbidden-field evidence.

### 6.9 Incomplete or General Runtime-Control Service Operation Rejected

```yaml
test_case:
  id: "n6_user_web_bounded_rebind_incomplete_reject"
  type: "gate"
  purpose: "Reject ownership ambiguity, drift, multi-service scope, retry, and general service commands."
  input:
    task: "Restart an N6 service without complete ownership and Release lineage proof."
    layer_role: "runtime_control"
    affected_files: []
    risk_level: "critical"
    policy_id: "n6_user_web_immutable_release_bounded_rebind_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: false
  expected:
    compiler_status: "failed"
    decision_state: "REJECT"
    gate_status: "REJECT"
    binding_status: "not_applicable"
    trace_status: "passed"
    sandbox_status: "passed"
    final_status: "STOP"
    failure_category: "decision failure"
```

### 6.10 Exact N6 Strategy Center Scheduled Evaluator Accepted

```yaml
test_case:
  id: "n6_strategy_center_display_only_scheduled_evaluator_accept"
  type: "gate"
  purpose: "Accept only the exact immutable five-second scheduled run-once evaluator after its bounded canary."
  input:
    task: "Activate only com.ashare-v3.n6.strategy-center-evaluator-v1 after the frozen 20260722 canary PASS."
    layer_role: "N6_user"
    affected_files: []
    risk_level: "critical"
    policy_id: "n6_strategy_center_display_only_scheduled_evaluator_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: true
  expected:
    compiler_status: "passed"
    decision_state: "ACCEPT"
    gate_status: "ACCEPT"
    binding_status: "ACCEPT"
    trace_status: "passed"
    sandbox_status: "passed"
    final_status: "EXECUTE"
    failure_category: "none"
```

The fixture for this case must satisfy every machine-readable field in
`docs/EXECUTION_KERNEL.md`; the abbreviated YAML above is not authority to omit
the bounded-canary artifact, exact Release/runner/planner/dependency/runtime-env/
argv/hash evidence, exact label/plist/interval/PGSERVICE, current-open-day gate,
closed-day no-op, per-user
isolation, exact four-table DML list, observation scope/grain/surface/dedup/
replay, Web function-only and virtual-executor observation disjointness,
observation-preserving exact-label/plist rollback, V2-dependent 081 rollback
rejection, both no-overlap guards, before/readiness/rollback/concurrency
evidence, executor guard, or forbidden-field evidence.

### 6.11 Incomplete, Drifted, or Unsafe Scheduled Evaluator Rejected

```yaml
test_case:
  id: "n6_strategy_center_scheduled_evaluator_incomplete_reject"
  type: "gate"
  purpose: "Reject missing canary, non-open date, drift, overlap, mutable code, extra DML/service, and trading paths."
  input:
    task: "Start a recurring strategy evaluator without complete canary and current-open-day evidence."
    layer_role: "N6_user"
    affected_files: []
    risk_level: "critical"
    policy_id: "n6_strategy_center_display_only_scheduled_evaluator_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: false
  expected:
    compiler_status: "failed"
    decision_state: "REJECT"
    gate_status: "REJECT"
    binding_status: "not_applicable"
    trace_status: "passed"
    sandbox_status: "passed"
    final_status: "STOP"
    failure_category: "decision failure"
```

Additional scheduled negative fixtures must reject a fifth table, incomplete
observation scope predicate/insert columns, non-081 grain, cross-scope/date
write, same-episode dual surfaces, duplicate observation changes, wrong
`surface_kind`, replay drift, Web/virtual-executor observation table authority,
executor observation code references, observation-deleting rollback, and 081
schema rollback while a V2 dependency exists.

### 6.12 Exact N6 Strategy Center 081 Maintenance Window Accepted

```yaml
test_case:
  id: "n6_strategy_center_081_maintenance_window_accept"
  type: "gate"
  purpose: "Accept only one prepare-081 quiesce window without migration authority."
  input:
    task: "Close Strategy Center selection writes, quiesce only its evaluator, and freeze one maintenance token."
    layer_role: "runtime_control"
    affected_files: []
    risk_level: "critical"
    policy_id: "n6_strategy_center_schema_migration_maintenance_window_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: true
  expected:
    compiler_status: "passed"
    decision_state: "ACCEPT"
    gate_status: "ACCEPT"
    binding_status: "ACCEPT"
    trace_status: "passed"
    sandbox_status: "passed"
    final_status: "EXECUTE"
    failure_category: "none"
```

The fixture must satisfy every machine-readable Kernel field. In particular it
must prove the Web-only `1→0` strategy-write delta, state-driven one-attempt Web
restart, one evaluator bootout with zero bootstrap, evaluator PID/job absence,
four-table read-only watermark scope, immutable token hashes/mode/expiry,
virtual-executor object disjointness, and zero migration/database-write attempt.
This case authorizes only maintenance-window preparation, not 081 itself.

### 6.13 Incomplete or Unsafe 081 Maintenance Window Rejected

```yaml
test_case:
  id: "n6_strategy_center_081_maintenance_window_incomplete_reject"
  type: "gate"
  purpose: "Reject missing authorization, drift, migration, virtual-executor operation, retry, and business paths."
  input:
    task: "Prepare or execute Strategy Center maintenance without complete quiesce and token evidence."
    layer_role: "runtime_control"
    affected_files: []
    risk_level: "critical"
    policy_id: "n6_strategy_center_schema_migration_maintenance_window_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: false
  expected:
    compiler_status: "failed"
    decision_state: "REJECT"
    gate_status: "REJECT"
    binding_status: "not_applicable"
    trace_status: "passed"
    sandbox_status: "passed"
    final_status: "STOP"
    failure_category: "decision failure"
```

The reject matrix must include: absent current-request authorization; migration
other than exact 081; 082/083 inclusion; Web writes still enabled; evaluator
loaded or PID present; token missing, expired, writable, or hash-drifted;
Release/migration/plist/runner/ACL/ownership drift; any virtual-executor
operation; fixed sleep, kill, kickstart, retry, extra service; database write or
lock; old-V1-evaluator restore; N1-N5, queue, proposal/order/trade/position/cash,
or broker effects. A normal StartInterval PID/runs change alone must remain
accepted when frozen configuration and object authority are unchanged.

### 6.14 Exact Strategy Center Post-081 V2 Web Rebind Accepted

```yaml
test_case:
  id: "n6_strategy_center_post_081_v2_web_rebind_accept"
  type: "gate"
  purpose: "Accept one post-081 V2 Web rebind with strategy writes disabled and both non-Web services untouched."
  input:
    task: "Rebind only the N6 Web to the verified V2 Release after 081."
    layer_role: "runtime_control"
    affected_files: []
    risk_level: "critical"
    policy_id: "n6_strategy_center_post_081_v2_web_bounded_rebind_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: true
  expected:
    compiler_status: "passed"
    decision_state: "ACCEPT"
    gate_status: "ACCEPT"
    binding_status: "ACCEPT"
    trace_status: "passed"
    sandbox_status: "passed"
    final_status: "EXECUTE"
    failure_category: "none"
```

The fixture must satisfy every machine-readable Kernel field. It must prove
committed 081 and absent 082/083; source/target immutable hashes and
V2/081/non-regression; strategy write `0` before/target/after/rollback;
evaluator job/PID absence; frozen, write-disjoint virtual-executor
configuration; one Web bootout/bootstrap pair, zero retries, bounded
readiness/stability, and one conditional frozen-source rollback. It authorizes
no database, migration, evaluator, virtual-executor, business, or trading path.

### 6.15 Incomplete or Unsafe Post-081 V2 Web Rebind Rejected

```yaml
test_case:
  id: "n6_strategy_center_post_081_v2_web_rebind_incomplete_reject"
  type: "gate"
  purpose: "Reject write-enable, evaluator/virtual-executor operation, drift, migration, retry, and business paths."
  input:
    task: "Rebind the post-081 Web without complete immutable and quiescence evidence."
    layer_role: "runtime_control"
    affected_files: []
    risk_level: "critical"
    policy_id: "n6_strategy_center_post_081_v2_web_bounded_rebind_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: false
  expected:
    compiler_status: "failed"
    decision_state: "REJECT"
    gate_status: "REJECT"
    binding_status: "not_applicable"
    trace_status: "passed"
    sandbox_status: "passed"
    final_status: "STOP"
    failure_category: "decision failure"
```

The reject matrix must include: absent current-request authorization; 081 not
committed; 082/083 executed or requested; strategy write `1` before, target,
after, or rollback; evaluator job/PID present or any evaluator operation;
virtual-executor stop/start/restart/modification or
plist/Release/runner/role/ACL/object-boundary drift; missing immutable,
V2/081/non-regression, ownership, readiness, or rollback evidence; fixed sleep,
kill, kickstart, repeated primary attempt, extra service, database, migration,
N1-N5, queue, proposal/order/trade/position/cash, broker, or mutable-Release
path. A normal virtual-executor StartInterval PID/runs change alone must remain
accepted when all frozen configuration and object-boundary evidence is stable.

### 6.16 Exact Post-081 082/083 Catalog Migration Phase Accepted

```yaml
test_case:
  id: "n6_strategy_center_post_081_v2_catalog_migration_accept"
  type: "gate"
  purpose: "Accept exactly one ordered 082 or 083 transaction."
  input:
    layer_role: "N6_user"
    policy_id: "n6_strategy_center_post_081_v2_catalog_migration_window_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: true
  expected:
    kernel_decision: "ACCEPT"
    gate_decision: "ACCEPT"
    final_status: "EXECUTE"
```

The 082 fixture must prove committed 081, absent 082/083, pending count zero,
exact hashes, install-only schema/ACL scope, no compensation call, and no row
mutation. The separate 083 fixture must prove committed 081/082, absent 083,
passed 082 postflight/ACL, open trade date, pending and V2 selection counts
zero, unique active V1 coverage, and only the four catalog transitions. Both
require strategy write `0`, evaluator absence, frozen virtual-executor
evidence, one transaction/forward attempt, zero retry, and no same-request
rollback.

### 6.17 Unsafe or Misordered Post-081 Catalog Migration Rejected

```yaml
test_case:
  id: "n6_strategy_center_post_081_v2_catalog_migration_reject"
  type: "gate"
  purpose: "Reject combined, misordered, drifted, or over-broad migration."
  input:
    layer_role: "N6_user"
    policy_id: "n6_strategy_center_post_081_v2_catalog_migration_window_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: false
  expected:
    kernel_decision: "REJECT"
    gate_decision: "REJECT"
    final_status: "STOP"
```

The reject matrix must cover missing current-request authorization; combined or
misordered 082/083; pending revisions; V2 selection items before 083; write
flag or evaluator drift; Release/migration/plist/ACL/ownership drift; an 082
compensation-function call; selection/projection/change writes; Web or virtual
executor operation; extra migration/service; retry or same-request rollback;
business DML, N1-N5, queue, broker, and trading effects. General runtime and
database writes remain `REJECT`.

### 6.18 Exact Post-083 Single-User Pending V2 Revision Accepted

```yaml
test_case:
  id: "n6_strategy_center_post_083_single_user_pending_v2_revision_accept"
  type: "gate"
  input:
    layer_role: "N6_user"
    policy_id: "n6_strategy_center_post_083_single_user_pending_v2_revision_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: true
  expected:
    kernel_decision: "ACCEPT"
    gate_decision: "ACCEPT"
    final_status: "EXECUTE"
```

The fixture must first prove `pre_dml_guard_harness_recovery_v2`: exactly two
ordered historical pre-DML harness transactions automatically aborted, first
at SQLSTATE `42704` in the PUBLIC ACL audit guard, then at SQLSTATE `42601`
because the psql request-id variable inside dollar-quoted `DO` did not expand.
For both, official selection-function calls/revision-item DML/commits/mutation
attempts were all zero, the request id was not persisted, and every frozen
before/after hash is equal. The only ACL repair is audit-only
`pg_catalog.aclexplode(COALESCE(proacl,
pg_catalog.acldefault('f', proowner))).grantee=0`, the official selection
function remains unchanged, and a separate `READ ONLY` preflight transaction
completes every complex validation. The later independent request uses a new
request id supplied through shell/driver parameter binding; only its hash may
be audited and token/secret logging is forbidden. It must then freeze
principal/user 1/1, active V1 revision 15/no.5, current-open 20260723, target
no.6 with previous_revision_id 15, and exactly package_1/v1 -> package_1/v2. It
must satisfy every machine-readable policy field, use one owner/user-isolated
official function, preserve strategy
write `0`, keep evaluator quiesced and virtual executor unoperated, and create
only pending/pending revision plus item in at most one mutation attempt with
zero retry. The mutation transaction is limited to BEGIN/SET/advisory-lock
SELECT/one official function SELECT/read-only postflight SELECT/COMMIT and
forbids `DO`, psql variable interpolation, dynamic SQL, and complex validation.

### 6.19 Unsafe Post-083 Pending V2 Revision Rejected

```yaml
test_case:
  id: "n6_strategy_center_post_083_single_user_pending_v2_revision_reject"
  type: "gate"
  input:
    layer_role: "N6_user"
    policy_id: "n6_strategy_center_post_083_single_user_pending_v2_revision_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: false
  expected:
    kernel_decision: "REJECT"
    gate_decision: "REJECT"
    final_status: "STOP"
```

The reject matrix must cover historical official-function call, revision/item
DML, commit, mutation attempt, persisted or reused request id, unequal
before/after hash, changed failure order/reason, a third pre-DML error kind, a
third harness transaction, non-audit guard repair, official selection-function
change, failed/non-read-only preflight, mutation `DO`, psql interpolation,
dynamic SQL, secret leakage, or second mutation attempt. It must also cover missing
authorization, all-users/multi-scope, non-current or closed trade date,
package-key changes, strategy write `1`, Web PUT, evaluator
presence/operation, missing or drifted 083 postflight, existing pending/V2
item, predecessor drift, activation, 082 compensation call,
projection/change/catalog/schema/extra-table writes, retries, N1-N5,
virtual-executor operation, queues, business, broker, and trading effects.
General database/runtime execution and all existing policy boundaries remain
`REJECT`.

### 6.20 Remaining-Users Pending V2 Revision Accepted Contract

```yaml
test_case:
  id: "n6_strategy_center_post_083_remaining_users_pending_v2_revision_accept"
  type: "gate"
  input:
    layer_role: "N6_user"
    policy_id: "n6_strategy_center_post_083_remaining_users_pending_v2_revision_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: true
  expected:
    kernel_decision: "ACCEPT"
    gate_decision: "ACCEPT"
    final_status: "EXECUTE"
```

The fixture must supply one non-hard-coded principal/user, its active V1
predecessor, current N6 authority date, predecessor+1 target revision and the
same package-key set at v2. It must prove owner-isolated function attestation,
strategy write `1`, no Web PUT, evaluator observation without operation, one
transaction/attempt, zero retry, pending/pending postflight and unchanged
other-user/projection/change watermarks. The predicted diff is only the two
selection tables.

### 6.21 Remaining-Users Pending V2 Revision Rejected Contract

The reject matrix must cover all-users/multi-scope, fixed first-user scope,
non-current date, predecessor or package-key drift, missing owner-function
attestation (`scope_expansion_required=owner_selection_function`), Web PUT,
evaluator/executor operation, activation, extra table, retry, projection/change
or business/trading/N1-N5 writes. The existing session-token Web function and
manual SQL must be rejected as creation authority; general runtime and
database writes remain `REJECT`.

## 7. Acceptance Criteria

The Execution Test Suite is valid only if it can evaluate:

```text
valid DAG acceptance
invalid DAG rejection
decision state correctness
gate enforcement correctness
binding order correctness
trace completeness
sandbox no-write guarantee
failure categorization
replayability of failures and accepted paths
```

## 8. Non-Goals

This document does not define:

```text
test runner implementation
Python tests
database tests
runtime execution tests
worker tests
N1-N6 behavior changes
schema changes
CI integration
```

## 9. Golden Rule

No execution-control path is valid unless it passes structure, decision, enforcement, trace, and sandbox expectations for its declared mode.
### 6.20 Reviewed-view Date Authority and Write-Restore Policies

Static policy tests must parse the machine-readable blocks for
`n6_strategy_center_reviewed_view_date_authority_084_v1` and
`n6_strategy_center_post_canary_web_write_restore_v1`. They must reject a
missing or non-singleton three-view `for_trade_date` consensus, any
`common_trade_calendar` or N1-N5 raw-table authority, source/card watermark
drift, a second 084 attempt, a compensation call, or a nonzero strategy-write
flag. Write restore additionally requires canary PASS, 12 stable evaluator
ticks, pending `0`, exact Web ownership/hash stability, and one bootout plus one
bootstrap; general runtime and database writes remain `REJECT`.

### 6.22 Resumable WEB/EVALUATOR Target Split

Static tests for `n6_strategy_center_shadow_activation_grant_v1` must prove
that four user-visible stages remain unchanged while
`BOUNDED_REBIND` resumes from its failed evidence into exactly two internal
checkpoints. WEB_TARGET alone may be planned and leased in this governance
closeout; it binds d85/ee2b/write `0` to immutable f464 and requires Evaluator
job absent/runner `0`. EVALUATOR_TARGET must remain
`blocked_pending_canary`, reject planning and leasing before WEB_TARGET passed
plus current-date bounded-canary PASS, and later target the same f464 only.

The suite must also prove the `72b1d50` control-plane ancestry, candidate/
canonical/API/085/086 non-regression, d85 bundle historical supersession by the
f464 `6efda630...`/`119296de...` bundle, zero Virtual Executor/N1-N5/trading
authority, and append-only failed-checkpoint resume semantics. It must retain
the separate `n6_strategy_center_pre_canary_web_write_quiesce_v1` Gate3+
contract and require strategy-write `0` for both bounded canary and scheduled
evaluator.
