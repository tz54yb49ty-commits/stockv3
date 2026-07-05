# Execution Compiler

## 1. Purpose

The Execution Compiler converts natural language tasks into a deterministic execution DAG.

It exists to make task planning explicit before any approved action is performed. The compiler translates a user request into ordered nodes and dependency edges so that validation, modification, verification, and finalization are visible and auditable.

This is a documentation-only system. It introduces no runtime implementation, no execution logic, no code changes, no database behavior, and no N1-N6 system change.

## 2. Execution Plan Schema

The compiler output is a YAML `execution_plan`.

```yaml
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
```

`nodes` define the work units. `edges` define dependency order between work units.

## 3. Node Types

### PLAN

Defines the intended work, scope, layer boundary, affected files, and risk level.

### VALIDATE

Checks that prerequisites, constraints, layer boundaries, and approved affected files are valid before any modification.

### MODIFY

Represents an approved file change. Every `MODIFY` node must be preceded by at least one `VALIDATE` node.

### VERIFY

Checks that the modification matches the approved plan and does not affect unapproved files or layers.

### FINALIZE

Produces the final status, summary, and audit-ready completion record.

## 4. Rules

```text
No execution without DAG.
Every MODIFY must be preceded by VALIDATE.
No cross-layer operations allowed.
No cycles in DAG.
```

Detailed rules:

1. A task must have an `execution_plan` before any approved action is performed.
2. The DAG must include `nodes` and `edges`.
3. A `MODIFY` node is invalid unless a dependency path from `VALIDATE` to `MODIFY` exists.
4. A DAG must not contain cycles.
5. Every node must declare its `layer_role`.
6. Every node must stay within the approved `layer_role`.
7. Every node must stay within the approved `affected_files`.
8. Cross-layer operations are rejected.
9. Runtime execution, database writes, worker startup, outbox consumption, rollback execution, and real trading are outside this documentation-only compiler contract.

## 5. Output Format

The compiler output must be YAML:

```yaml
execution_plan:
  plan_id: "example_plan"
  layer_role: "runtime_control"
  risk_level: "low"
  affected_files:
    - "docs/EXAMPLE.md"

  nodes:
    - id: "plan"
      type: "PLAN"
      description: "Define documentation-only change."
      layer_role: "runtime_control"
      affected_files:
        - "docs/EXAMPLE.md"

    - id: "validate"
      type: "VALIDATE"
      description: "Validate scope and file boundary."
      layer_role: "runtime_control"
      affected_files:
        - "docs/EXAMPLE.md"

    - id: "modify"
      type: "MODIFY"
      description: "Create the approved documentation file."
      layer_role: "runtime_control"
      affected_files:
        - "docs/EXAMPLE.md"

    - id: "verify"
      type: "VERIFY"
      description: "Confirm only approved file changed."
      layer_role: "runtime_control"
      affected_files:
        - "docs/EXAMPLE.md"

    - id: "finalize"
      type: "FINALIZE"
      description: "Return final execution status."
      layer_role: "runtime_control"
      affected_files:
        - "docs/EXAMPLE.md"

  edges:
    - from: "plan"
      to: "validate"
      reason: "Validation follows planning."

    - from: "validate"
      to: "modify"
      reason: "Modification requires prior validation."

    - from: "modify"
      to: "verify"
      reason: "Verification follows modification."

    - from: "verify"
      to: "finalize"
      reason: "Finalization follows verification."
```

## 6. Golden Rule

No execution without a valid acyclic execution DAG.
