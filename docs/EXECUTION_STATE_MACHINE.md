# Execution State Machine

## 1. States

The execution state machine is deterministic and documentation-only.

It defines the required state chain for Codex-controlled execution in A股监控系统 v3. It introduces no runtime implementation, no code, no database behavior, and no N1-N6 system change.

Supported states:

```text
IDLE
NORMALIZED
KERNEL_EVALUATED
GATE_EVALUATED
BINDING_CHECKED
TRACE_RECORDED
EXECUTED
STOPPED
```

State definitions:

```text
IDLE
  No task has entered the execution chain.

NORMALIZED
  The user request has been converted into kernel_input.

KERNEL_EVALUATED
  Execution Kernel has returned ACCEPT / REJECT / BLOCK / ESCALATE.

GATE_EVALUATED
  Runtime Gate has evaluated the Kernel output.

BINDING_CHECKED
  Binding Rule has verified Kernel and Gate invocation order and decision presence.

TRACE_RECORDED
  Execution Trace entry has been produced for the full decision chain.

EXECUTED
  The approved action has been performed.

STOPPED
  Execution has stopped because a decision rejected, blocked, escalated, or failed.
```

## 2. Transitions

Valid transitions:

```text
IDLE -> NORMALIZED
NORMALIZED -> KERNEL_EVALUATED
KERNEL_EVALUATED -> GATE_EVALUATED
GATE_EVALUATED -> BINDING_CHECKED
BINDING_CHECKED -> TRACE_RECORDED
TRACE_RECORDED -> EXECUTED
TRACE_RECORDED -> STOPPED
```

No other transition is valid.

Deterministic transition chain:

```text
IDLE
  -> NORMALIZED
  -> KERNEL_EVALUATED
  -> GATE_EVALUATED
  -> BINDING_CHECKED
  -> TRACE_RECORDED
  -> EXECUTED / STOPPED
```

## 3. Hard Rules

```text
No skipping states.
No backward transitions.
No direct EXECUTE without full state chain.
Any missing state = STOP.
```

Detailed rules:

1. A task must begin at `IDLE`.
2. A task must pass through every intermediate state in order.
3. `EXECUTED` is reachable only from `TRACE_RECORDED`.
4. `STOPPED` is reachable only after the decision chain is traceable.
5. A task cannot return to an earlier state.
6. A task cannot jump from `NORMALIZED`, `KERNEL_EVALUATED`, `GATE_EVALUATED`, or `BINDING_CHECKED` directly to `EXECUTED`.
7. If any required state is missing, the task must stop.

## 4. Failure Handling

If any stage fails, the state machine must transition to `STOPPED`.

Failure cases include:

```text
Kernel returns REJECT / BLOCK / ESCALATE
Runtime Gate returns REJECT / BLOCK / ESCALATE
Binding Rule fails
Trace cannot be recorded
Required state is missing
Out-of-order transition is detected
Cross-layer violation is detected
Runtime execution is requested without authorization
```

Failure handling rule:

```text
failure -> TRACE_RECORDED -> STOPPED
```

Even when execution stops, the system must still generate a trace entry. The trace must identify the failed state, decision origin, reason, and final status.

## 5. Replay Compatibility

The state machine must support full replay of the execution path.

Replay must reconstruct:

```text
full execution path
failure point
decision origin
```

Decision origin must identify whether the decisive outcome came from:

```text
Execution Kernel
Runtime Gate
Binding Rule
Trace System
State Machine
```

Replay requirements:

1. Every transition must be reconstructable from the trace.
2. The replay must show the exact state sequence from `IDLE` to `EXECUTED` or `STOPPED`.
3. The replay must identify the first failed state when final status is `STOPPED`.
4. The replay must identify the decision origin as Kernel, Gate, Binding, Trace, or State Machine.
5. A replay with missing states, partial decisions, or overwritten history is invalid.

## 6. Golden Rule

No execution may occur unless the full deterministic state chain is completed and traced.
