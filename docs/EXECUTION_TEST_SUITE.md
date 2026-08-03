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
Runtime execution request must produce REJECT unless it fully satisfies one applicable named fail-closed policy.
Ambiguous task must stop.
An accepted named runtime policy must use decision state `ACCEPT` plus exactly
`policy_id=n6_strategy_center_display_only_bounded_run_once_v1`,
`policy_id=n6_strategy_center_display_only_scheduled_evaluator_v1`, or
`policy_id=n6_user_web_immutable_release_bounded_rebind_v1`, or
`policy_id=n6_strategy_center_schema_migration_maintenance_window_v1`, or
`policy_id=n6_strategy_center_post_081_v2_web_bounded_rebind_v1`, or
`policy_id=n6_strategy_center_pre_canary_web_write_quiesce_v1`, or
`policy_id=n6_strategy_center_post_083_v2_web_bounded_rebind_v1`, or
`policy_id=n6_strategy_center_post_081_v2_catalog_migration_window_v1`, or
`policy_id=n6_immutable_release_install_bounded_v1`, or
`policy_id=n6_immutable_release_install_pre_rename_validator_recovery_v1`, or
`policy_id=n6_immutable_release_install_preflight_git_violation_recovery_v1`, or
`policy_id=n4_lifecycle_deactivation_state_columns_controlled_promotion_v1`.
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
exact bounded N6 strategy policy with every authority field -> ACCEPT
exact N6 strategy scheduled-evaluator policy with every authority field -> ACCEPT
exact bounded N6 Web immutable Release rebind policy with every authority field -> ACCEPT
exact N6 Strategy Center 081 maintenance-window policy with every authority field -> ACCEPT
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
runtime_execution_requested=true only when the exact named policy independently passed
```

Negative cases:

```text
kernel_output missing -> REJECT
kernel_evaluated=false -> REJECT
kernel_decision=REJECT -> STOP
kernel_decision=BLOCK -> STOP
kernel_decision=ESCALATE -> STOP
cross_layer_violation_detected=true -> REJECT
runtime_execution_requested=true without the exact passed named policy -> REJECT
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
runtime execution request without the exact named policy produces ACCEPT
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
    affected_resources:
      - string
    policy_id: string | null
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

### 6.20 Exact Evaluator Quiesce for Web Rebind Accepted

```yaml
test_case:
  id: "n6_strategy_center_evaluator_quiesce_for_web_rebind_accept"
  type: "gate"
  purpose: "Accept one exact evaluator bootout before a separately authorized Web rebind."
  input:
    task: "Quiesce only the exact Strategy Center evaluator in post-083 write-enabled state."
    layer_role: "runtime_control"
    affected_files: []
    risk_level: "high"
    policy_id: "n6_strategy_center_evaluator_quiesce_for_web_rebind_v1"
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

The complete fixture must prove post-083 state, strategy write `1`, exact
evaluator plist/path/runner/Release/role/ACL/launchd ownership and state, one
bootout, zero bootstrap/retry, state-driven PID/job absence, unchanged Web,
frozen and unoperated write-disjoint virtual executor, and zero database,
migration, business, trading, or N1-N5 effects.

### 6.21 Unsafe Evaluator Quiesce for Web Rebind Rejected

```yaml
test_case:
  id: "n6_strategy_center_evaluator_quiesce_for_web_rebind_reject"
  type: "gate"
  purpose: "Reject incomplete, ambiguous, repeated, cross-service, database, or business quiesce requests."
  input:
    task: "Stop an evaluator without the complete exact-label quiesce contract."
    layer_role: "runtime_control"
    affected_files: []
    risk_level: "high"
    policy_id: "n6_strategy_center_evaluator_quiesce_for_web_rebind_v1"
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

The reject matrix must include missing current authorization; wrong
layer/label/plist/phase; strategy write not `1`; ambiguous ownership; missing or
drifted plist/runner/Release/role/ACL/state; more than one target; bootstrap,
kickstart, kill/signal, retry or automatic restore; Web or virtual-executor
operation; virtual-executor configuration/ACL/object-boundary drift; database,
migration, evaluator execution, selection/projection/change, queue, N1-N5,
business, broker, or trading paths. Its normal five-second PID/runs cycling
alone must remain accepted.

### 6.20A Exact Post-083 V2 Web Bounded Rebind Accepted

```yaml
test_case:
  id: "n6_strategy_center_post_083_v2_web_bounded_rebind_accept"
  type: "gate"
  input:
    layer_role: "runtime_control"
    policy_id: "n6_strategy_center_post_083_v2_web_bounded_rebind_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: true
  expected:
    compiler_status: "passed"
    kernel_decision: "ACCEPT"
    gate_decision: "ACCEPT"
    sandbox_status: "passed"
    final_status: "EXECUTE"
```

The positive fixture must prove committed 081/082/083/084; exact legacy source
`20260724_042200__a1dc7350`; closure to full commit
`a1dc73503a07055f7bdb9cd29b378d1272642473`, tree, archive, git-ls-tree,
manifest, filesystem, path/blob/mode, ownership, and immutable attestation;
one-time rollback-only source use; one target with a formal 40-character
commit-bound name and complete immutable, source-delta, non-regression, V2, and
schema proof; strategy write `1` before/target/after/rollback; a passed
independent evaluator-quiesce gate with job/PID absent and zero evaluator
operations; frozen, write-disjoint virtual-executor `StartInterval=5` evidence
with zero executor operations; one Web bootout/bootstrap, zero retries,
60-second readiness, 30-second stability, and one conditional exact-source
rollback. Normal virtual-executor PID/runs cycling alone remains accepted.

### 6.21A Unsafe Post-083 V2 Web Rebind Rejected

```yaml
test_case:
  id: "n6_strategy_center_post_083_v2_web_bounded_rebind_reject"
  type: "gate"
  input:
    layer_role: "runtime_control"
    policy_id: "n6_strategy_center_post_083_v2_web_bounded_rebind_v1"
    runtime_execution_requested: true
    named_policy_evaluated: true
    named_policy_passed: false
  expected:
    compiler_status: "failed"
    kernel_decision: "REJECT"
    gate_decision: "REJECT"
    sandbox_status: "passed"
    final_status: "STOP"
```

The reject matrix must cover missing authorization; uncommitted/drifted
081/082/083/084 evidence; any source other than the exact legacy basename;
short/full commit mismatch; missing tree/archive/git-ls-tree/manifest/
filesystem/blob-mode-path/ownership closure; source reuse, mutation, or target
use; short or non-commit-bound target; target lineage/schema/N6 regression;
strategy write `0`; evaluator not independently quiesced, job/PID present, or
any evaluator operation; virtual-executor operation or configuration/ACL/object
drift; multiple services, releases, attempts, retries, fixed sleeps,
signal/kill/kickstart, extra environment delta, mutable Release, database,
migration, selection/projection/change, queue, N1-N5, proposal/order/trade/
position/cash, broker, or trading effects. All existing Web policy matrices
must remain byte-for-byte semantically strict and general runtime execution
must remain `REJECT`.

## 7. Acceptance Criteria

### 6.22 N6 Immutable Release Install Artifact-Only Policy

`policy_id=n6_immutable_release_install_bounded_v1`

Static tests must accept one explicitly authorized target whose commit/tree/
archive/manifest/filesystem/attestation hashes are verified, whose target is a
new direct child, and whose unique same-parent staging directory is validated
before one atomic rename. The matrix must reject target existence, hash or
metadata drift, staging outside the root, non-atomic finalization, retries,
existing-release deletion, LaunchAgent/service/database/evaluator operations,
and all business or N1-N6 writes. It must also accept exactly one frozen
owner-only root-mode window `0555 -> 0755 -> 0555`, and reject owner/group/
ACL/xattr drift, group/other write, missing restoration, a writable final root,
or repeated mode changes. Failed cleanup may remove only newly created paths.

### 6.22A N6 Immutable Release Pre-Rename Validator Recovery Policy

`policy_id=n6_immutable_release_install_pre_rename_validator_recovery_v1`

Static tests must accept only the exact aa6d19c BLOCKED attestation and
sidecar, source hashes, zero prior rename/fallback/retry/cleanup attempts,
absent target, restored `0555` Release root, unchanged existing Releases and
the frozen staging-v1 path/device/inode/owner/mode/count/ACL/xattr
fingerprints. Every historical identity, path, hash, status, blocker and count
is an exact literal; another syntactically valid SHA must still be rejected.

Tests must require the one later recovery request to generate exactly one new
SHA-bound validator capability attestation and sidecar under exact new
artifact directories, seal files/directories to `0444/0555`, bind the
`/usr/bin/xattr` executable and protocol hashes, and prove that xattr names and
values can be read without mutation or unsupported-API fallback. They must
prove this phase completed before root chmod or staging-v2 creation and that
capability failure stops before either mutation, confirms root remains `0555`,
and FINALIZE writes/seals the exact recovery failure artifacts before STOP.
Only the exact fresh
same-parent staging-v2 may then be materialized from the frozen archive and
fully validated with exact owner/group before one same-root-dirfd
`renameatx_np` using EXCL/NOFOLLOW_ANY/RESOLVE_BENEATH and one new root
`0555 -> 0755 -> 0555` window; root restoration must precede target postflight
and attestation writes. The matrix must reject missing or partial
capability evidence, another staging name, staging-v1 reuse/modification/
rename/deletion/cleanup, target existence, source or existing-Release drift,
repeated recovery, automatic retry, EACCES/host/privileged policy fallback,
cleanup, non-atomic finalization and every Git, test, port, service,
LaunchAgent, database, evaluator/executor, migration, N1-N6, business or
trading operation. It must also assert that the governance definition gate
cannot execute the recovery and that staging-v1 never appears in allowed
mutation resources or operations.

Tests must reject unknown request keys and every ordinary, overwrite-capable,
absolute-path, parent-traversal or missing-flag rename. They must bind the
exact new recovery output root/directory, validation JSON, install-attestation
JSON and SHA sidecar; prove all were absent, written once, hash-bound and
sealed `0444/0555`; and reject preexistence, overwrite or any unbound external
write. Tests must prove no recovery output path is created until the Release
root is restored or confirmed unchanged at `0555` and the selected recovery
outcome branch, including capability failure, has completed sealing and
postflight; early creation during the root
window, staging work, rename or Release postflight must reject. Tests must
cover failure after output-root create, directory create, each of
the three writes and final seal; every branch must seal created paths
`0444/0555`, record partial identity/hash evidence and reject writable
residue. New staging and target UID:GID must both be the frozen `501:20`.

The generated capability attestation and sidecar hashes are phase-local
values, not predeclared historical hashes. A 64-hex shape alone is
insufficient: tests must enforce the literal frozen `/usr/bin/xattr` and
canonical validator-protocol hashes, sidecar-to-attestation hash equality,
attestation-embedded executable/protocol hash equality, no duplicate JSON
keys, one generation/probe/write, exact new paths, and before/after
immutability. Operation ordering must be probe -> attestation generation ->
sidecar/hash/seal -> capability verification -> root write, and rename ->
root restoration -> target postflight/attestation. Another valid SHA in only
one member of any binding pair must
reject. Any pre-rename failure after staging-v2 creation must seal all created
files/directories to `0444/0555`, attest identity/metadata and leave no
writable staging. A post-rename postflight failure must preserve an immutable
target without modification or deletion; pre-rename validation names
staging-v2, while target content/owner/mode/ACL/link postflight occurs only
after rename.

The xattr-value matrix must bind the fourth field of the exact frozen
`release-content-manifest.tsv`: 6243 unique strict-UTF-8 file paths, plus 45
derived directory paths including a zero-byte root representation, yielding
exactly 6288 records. The `.git-ls-tree.nul` blob count is 6254 and is not the
xattr path authority; the 11-path export-ignore difference must be asserted.
TSV parsing rejects extra tabs, CR, embedded LF/NUL, duplicates, absolute or
non-normalized paths. Each closure path must have exactly one
`com.apple.provenance`, zero other names and 11 raw bytes with raw-value SHA-256
`29056cd65452fb0f6214e35e97e773d512c87f3bdd3577f2cc445b082ae19487`
and canonical fingerprint SHA-256
`92d525c921324d35d82bc503142c5fe3bfab37fd09b199788053903013baa7ee`.
The protocol strips ASCII whitespace from `xattr -px` output, rejects
non-hex/odd-nibble output, decodes raw bytes, encodes root/non-root relative
paths deterministically, frames path/name/value with unsigned 64-bit
big-endian lengths, sorts by path/name bytes, and hashes concatenated records.
Fixtures must cover multiple paths/names, empty and binary values, order
independence, invalid hex and a single-value drift. A frozen-source
reconciliation test must re-hash the release-content manifest, its 6243-path
set and its 6288-path closure.

### 6.22B N6 Immutable Release Preflight Git Violation Recovery Policy

`policy_id=n6_immutable_release_install_preflight_git_violation_recovery_v1`

Static tests bind the prior governance literals, failure status/type, unique
JSONL path/session/turn identities, line/byte boundaries, stable
segment/prefix SHA-256 values, sole Git tool-call raw/argument/output hashes
and ordered timeline. They accept only historical `rev-parse`, `diff`, and
`show`, while requiring zero stage/commit/checkout/switch/branch/push/worktree
change and zero capability/recovery-artifact/root-mode/staging-v2/target/
cleanup/fallback/runtime/database/service mutation.

Tests reject Git or tests in the later execution request and require equal
independently frozen/current `AGENTS.md` raw-byte hashes and Kernel
policy-block raw-byte hashes, stable session segment/prefix hashes and direct
filesystem evidence. They reject summary-only evidence, append-drifting
whole-session SHA authority, prior-policy reuse, another procedural recovery,
fallback or retry. Capability-first, fresh staging-v2, full blob/path/mode/
owner/ACL/xattr raw-value validation, one root `0555 -> 0755 -> 0555` window,
one exclusive same-dirfd rename and permanent staging-v1 evidence-only
constraints remain mandatory. The governance definition gate cannot execute.

### 6.22C N4 Lifecycle Deactivation State Columns Controlled Promotion Policy

`policy_id=n4_lifecycle_deactivation_state_columns_controlled_promotion_v1`

Static tests must prove `6d1b7a24` and `a1ff8b0e` are fixed, verified source
evidence only and are rejected as final execution targets. They bind source
base/endpoint/rollback trees, the exact eight-path allowlist, combined and
rollback patch SHA-256 values, all eight endpoint blob ids, and both exact
label/original-plist path/SHA pairs.

The policy must contain no literal not-yet-created final commit SHA. Tests
accept only an execution-time exact set where Active HEAD is the policy
commit, its parent is `8229124a`, final promotion consists of exactly two
direct-child commits, rollback is the final tip's direct child, and rollback
tree equals the policy commit tree. Final combined/rollback patch hashes,
changed paths and all eight blobs must equal the frozen source evidence;
parent, tree, patch, path or blob drift must reject.

Tests require tracked/index clean state, unchanged original plists, both
worker/child states idle, two exact bootouts, state-driven absence, one
ff-only merge and two original-plist bootstraps. They reject another label,
plist or path, fixed sleep, kickstart, manual execute, retry, non-ff merge,
push, checkout/rebase/cherry-pick, automatic rollback, DB DML, message/queue,
historical-event, N2/N3/N5/N6 and trading operations. Failure may report the
frozen rollback target only. The governance definition gate cannot execute.

### 6.23 N6 Immutable Release EACCES Retry Policy

`policy_id=n6_immutable_release_install_eacces_retry_v1`

Static tests must accept only one new staging/target pair after exactly one
frozen `EACCES` rename failure with an unchanged prior staging, absent target,
absent attestation and restored Release root. They must reject non-EACCES
causes, prior staging reuse or mutation, missing failure trace, root/staging
mode drift, group/other write, target existence, multiple retries, non-atomic
finalization and every service, database, evaluator, business, N1-N6 or
trading operation. The staging root's temporary owner-only mode window must be
one `0555 -> 0755 -> 0555` transition surrounding the one rename; final target
and Release root must both be `0555`.

### 6.24 N6 Immutable Release Host-EACCES Remediation Policy

`policy_id=n6_immutable_release_install_host_eacces_remediation_v1`

Static tests must accept only a hash-bound host trace proving `EACCES` for a
`0555` staging to both same-parent and `/tmp`, one unchanged orphaned staging,
and one distinct new staging/target. Tests must reject missing trace evidence,
orphaned staging reuse or mutation, mode/metadata drift, non-atomic promotion,
retries and all service/database/evaluator/business/trading paths.

### 6.25 N6 Immutable Release Privileged Atomic Install Policy

`policy_id=n6_immutable_release_privileged_atomic_install_v1`

Static tests must accept only a root-only, SHA/signature-attested helper that
uses fixed parent dirfd `renameatx_np` with exclusive/no-follow/beneath flags
for one new direct-child target. They must reject path escape, existing target,
hash drift, non-atomic fallback, repeat invocation, shell/copy/delete/overwrite,
xattr/ACL/chmod and all runtime/database/business/trading paths.

### 6.26 N6 Privileged Materialize-and-Install Policy

`policy_id=n6_immutable_release_privileged_materialize_and_install_v1`

Static tests must accept only the hash-bound d85df632 archive/manifest V2
helper: commit `d85df6328bde223e912dabc3bd65e16df984aa45`, tree
`d6d5ae1d68a1255ea9f05d8e7ce40a837a572ea1`, archive SHA
`49fb8729e6648f2b15e20d699d5f0f10a97bc1cbd5935cc31f5bb90a9de859ac`,
manifest SHA
`df698d8208977cd5a1d24c144260eb6ef0604f39be1f33f0b08af387027b6106`,
filesystem SHA
`5f600a1e1fbb7905968312387c0fc17acee09968a6dfb7d238a22d8d49152ad4`,
6240 files, and 45 directories. They must require parent-dirfd staging
creation, safe archive paths, no symlink/hardlink, exact file/directory count
and modes, strict PAX `g`/`x` records limited to `comment`/`path`, one
exclusive/no-follow/beneath promotion and an immutable
d85df632-named attestation. They must reject arbitrary or former f2b1 inputs,
shell, copy/delete/overwrite, xattr/ACL, retries and all runtime/database/
business/trading paths.

### 6.27 N6 Final-f67 Privileged Materialize-and-Install Policy

`policy_id=n6_immutable_release_privileged_materialize_and_install_f67_v1`

Static tests must accept only the dedicated f67 helper and exact frozen
commit `f67be0f538f7fdc0fe413ac98bbdc5b32a29661a`, tree
`997e12766f806cedf046484463d19318fb9e4a69`, archive SHA
`88ea81e1fda5b1f4b6864c959e91de798bf95272184877c36b32cfd77d12fcd5`,
git-ls-tree SHA
`e49924357270ac612e6c50da510f10a4bdd069bc983adca6928e5948342745e1`,
manifest SHA
`4976e9510da6792274e63ce168acecb3ef4e16b893547b2b5fb813953f97c494`,
filesystem SHA
`ae6aed7d6fd3fa17ecb8362b3b28c1ed95c0113c05ac7841842797aeb4488004`,
bundle payload/file SHA values in the Kernel policy, 6240 files, 45
directories and PAX counts 1/108. Tests must verify fresh `mkdirat`, strict
path/link/mode/PAX validation, sealed `0444/0555`, commit-bound target,
exclusive/no-follow/beneath promotion and immutable f67 attestation. They
must reject d85-helper reuse, old staging, arbitrary input/hash/path,
shell/delete/overwrite/xattr/ACL, retry and runtime/database/N1-N6/trading
paths.

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

### Strategy Center Gate3+ Policy Matrix

Static tests must prove:

- `n6_strategy_center_pre_canary_web_write_quiesce_v1` is the only pre-canary
  Web flag quiesce gate;
- pre-canary quiesce changes only exact-Web strategy-write `1 -> 0` on the
  unchanged d85 Release, requires evaluator absence, never operates the virtual
  executor, and restores only frozen flag `1` after real health failure;
- bounded canary and scheduled evaluator both reject unless strategy-write is
  exactly `0`;
- stock/index/board reviewed N6 `for_trade_date` consensus is accepted and
  missing/ambiguous/mismatched batches, `common_trade_calendar`, or N1-N5 raw
  authority are rejected;
- bounded canary uses a dynamic positive principal/user/revision and current
  natural reviewed events; historical date/revision bindings reject;
- scheduled evaluator is exact-label, five-second, one scope per tick,
  pending-first/active-round-robin and requires at least twelve stable ticks;
- Web strategy-write restore is one exact flag-only `0 -> 1` rebind after
  canary PASS, twelve ticks and pending zero;
- each of seven remaining users requires an independent one-scope CAS
  transaction with zero retry and unchanged other users/projection/change;
- V1 retirement is catalog-only and rejects while any active V1, pending
  revision, incomplete replay/isolation/projection/SSE proof or V2 dependency
  gap remains;
- general runtime/database writes, N1-N5, virtual-executor operations and all
  proposal/order/trade/position/cash paths remain default `REJECT`.

### Strategy Center 30-Day Isolation Decommission Matrix

The retirement override supersedes the historical Gate3+ matrix above. Static
tests must prove every lifecycle-registry retired policy id returns `REJECT`
before historical policy evaluation while historical policy blocks remain
present for audit.

For `n6_strategy_center_decommission_web_runtime_v1`, tests must accept only
the exact immutable Strategy Center-removal Web Release gate with write
`0/0/0`, absent/unrestored evaluator, one Web bootout/bootstrap, bounded
readiness/stability, conditional frozen-source rollback, optional
post-stability read-only evaluator artifact archive, and zero database,
virtual-executor, other-service, heartbeat, N1-N5, or trading operations.

For `n6_strategy_center_decommission_schema_archive_v1`, tests must accept only
one independent `N6_user` transaction moving the exact six tables and owned
sequences/indexes into a new owner-only schema, revoking archive `USAGE` from
the frozen Web role, worker, and `PUBLIC`, removing only exclusive
triggers/functions, preserving per-table count/hash/DDL/ACL/dependencies, and
binding a dedicated 30-day rollback. Tests must reject drop/truncate/row DML,
role/079 ACL/`n6_strategy`/`n6_ai_strategy_*`/Virtual Executor/N1-N5/trading
changes, retry, combined gates, missing evidence, automatic deletion, and
heartbeat operations.

Static discovery must prove only the two decommission policies are ACTIVE for
Strategy Center retirement. The governance-definition request itself must
remain `runtime_execution_requested=false`, and physical deletion after 30
days must remain `REJECT` without a new independent explicit authorization.
