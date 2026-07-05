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

The Kernel exists, the Kernel returned `ACCEPT`, no cross-layer violation is present, no runtime execution is requested, and the requested action remains within approved file and layer boundaries.

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
5. If `runtime_execution_requested` is true, the Gate returns `REJECT`.
6. If the requested action exceeds `affected_files` or declared `layer_role`, the Gate returns `REJECT`.

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
