# Execution Kernel

## 1. Purpose

The Execution Kernel is the decision-control layer for Codex actions in A股监控系统 v3.

It exists to prevent Codex from executing, modifying, or crossing project boundaries without an explicit decision gate. Every requested task must be parsed, normalized, evaluated, and approved by the Kernel before any file change or execution step is allowed.

The Kernel is documentation-only in this phase. It introduces no runtime logic, no code, no database changes, and no N1-N6 system behavior.

## 2. Kernel Input Schema

```yaml
kernel_input:
  intent:
    description: "What the user is asking Codex to do."
    type: string

  layer_role:
    description: "The project layer in which the request belongs."
    allowed_values:
      - runtime_control
      - N1_ingestion
      - N2_condition
      - N3_market_data
      - N4_trigger
      - N5_action
      - N6_user
    required: true

  affected_files:
    description: "Exact files that may be created or modified."
    type: list[string]

  data_flow:
    description: "Declared direction of system impact."
    allowed_direction: "N1 -> N2 -> N3 -> N4 -> N5 -> N6"
    rule: "Downstream must not mutate upstream; upstream must not perform downstream work."

  risk_level:
    description: "Estimated risk of the requested action."
    allowed_values:
      - low
      - medium
      - high
      - critical
```

## 3. Kernel Decision States

### ACCEPT

The request is clear, scoped to the declared `layer_role`, affects only allowed files, follows N1 -> N6 one-way data flow, and introduces no forbidden runtime execution.

Result: Codex may proceed with the requested action.

### REJECT

The request violates a hard project boundary.

Examples:

```text
cross-layer mutation
runtime execution
unauthorized code changes
touching src/ during documentation-only work
modifying existing files when only new documentation is allowed
```

Result: Codex must not proceed.

### BLOCK

The request may be valid, but required information is missing.

Examples:

```text
missing layer_role
missing affected_files
missing risk_level
unclear data_flow impact
missing authorization for a risky step
```

Result: Codex must stop and request clarification or required evidence.

### ESCALATE

The request requires a human decision, layer switch, or separate gate before it can continue.

Examples:

```text
task belongs to another layer_role
rollback implications are unclear
downstream references may exist
request may affect N1-N6 runtime semantics
```

Result: Codex must stop and hand off with explicit evidence and next-step guidance.

## 4. Hard Validation Rules

```text
cross-layer mutation detection = reject
missing layer_role = block
runtime execution = forbidden
ambiguity = stop
```

Detailed rules:

1. If the request attempts to mutate another layer, the Kernel returns `REJECT`.
2. If `layer_role` is missing or unclear, the Kernel returns `BLOCK`.
3. If the request includes runtime execution, worker startup, database writes, rollback execution, outbox consumption, or real trading, the Kernel returns `REJECT` for this phase.
4. If the request is ambiguous, Codex must stop before modifying files.
5. If the request affects files outside `affected_files`, the Kernel returns `REJECT`.
6. If the request violates one-way N1 -> N6 data flow, the Kernel returns `REJECT`.

## 5. Execution Flow

```text
1. parse request
2. normalize task
3. evaluate kernel
4. decision gate
5. execute only if ACCEPT
```

Expanded flow:

```text
parse request
  -> identify intent, layer_role, affected_files, data_flow, risk_level

normalize task
  -> convert the request into kernel_input
  -> remove assumptions
  -> mark missing fields

evaluate kernel
  -> apply hard validation rules
  -> detect cross-layer mutation
  -> detect forbidden runtime execution
  -> detect ambiguity

decision gate
  -> ACCEPT: continue
  -> REJECT: stop
  -> BLOCK: stop and request missing information
  -> ESCALATE: stop and hand off to the correct gate or layer

execute only if ACCEPT
  -> perform only the approved action
  -> touch only approved files
  -> do not introduce runtime behavior
```

## 6. Golden Rule

No execution without kernel approval.
