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
