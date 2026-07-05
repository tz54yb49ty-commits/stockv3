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
