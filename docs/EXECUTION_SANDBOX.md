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

Any cross-layer mutation, runtime execution request, database operation, worker startup, or N1-N6 mutation must produce a simulated STOP outcome.

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

Sandbox simulation is not execution.

No real change is allowed inside the sandbox.
