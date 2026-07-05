# Drift CI System

## 1. Purpose

The Drift CI System is a static, CI-style validation design for A股监控系统 v3.

It prevents future changes from drifting away from the canonical N1-N6 boundaries, signal semantics, and execution-control architecture. It is documentation and static validation only. It does not modify runtime behavior, database schema, worker behavior, outbox behavior, rollback behavior, or N1-N6 business logic.

The system is valid only if it can reject unsafe changes before they are accepted.

## 2. Enforcement Scope

The Drift CI System validates changed files before merge or acceptance.

Default CI mode should scan only files changed by the proposed change set. Full-repository scans are allowed as audits, but existing historical artifacts may require explicit baseline exceptions before full-scan enforcement is enabled.

Primary protected paths:

```text
src/ashare_v3/ingestion      N1_ingestion
src/ashare_v3/condition      N2_condition
src/ashare_v3/market         N3_market_data
src/ashare_v3/trigger        N4_trigger
src/ashare_v3/action         N5_action
src/ashare_v3/user           N6_user
scripts/
sql/
docs/
tests/
configs/
```

## 3. Drift Detection Categories

### 3.1 Cross-Layer Execution Drift

Detects code or scripts that import, invoke, or mutate responsibilities owned by another layer.

Reject examples:

```text
N1 imports N2-N5 logic.
N2 accesses runtime execution layers.
N3 executes N4/N5/N6.
N4 performs N5 action execution logic.
N5 performs N4 trigger matching logic.
N6 writes N1-N5 facts or raw trigger/action facts.
```

### 3.2 Legacy Signal Reintroduction

Detects active use of legacy 30m signal types:

```text
B_BUY_30M_VOL
S_SELL_30M_SHRINK
```

Active signal whitelist:

```text
B_BUY
S_SELL
BUY:FULL
SELL:FULL
BUY_HINT
SELL_HINT
```

Historical reports and compatibility documents may mention legacy signals only when explicitly marked as historical, compatibility, rollback, or migration evidence. Active decision paths must not use legacy 30m signal types.

### 3.3 Orchestration Leakage

Detects scripts or modules that perform multi-layer execution chains.

Reject examples:

```text
N3 -> N4 -> N5 -> N6 chain in one script.
N4 execute followed by N5 execute in the same script.
N5 execute followed by N6 projection in the same script.
Any run-once or worker script that executes multiple business layers sequentially.
```

Runtime control may register commands and display status, but it must not execute N1-N6 stage commands.

### 3.4 Architecture Boundary Violations

Detects changes that weaken canonical architecture boundaries.

Reject examples:

```text
Downstream layer writes upstream facts.
Upstream layer embeds downstream user policy.
Trigger layer writes action facts.
Action layer writes user projection.
Condition layer pulls realtime market data.
Market layer writes trigger/action/user state.
```

## 4. Static Checkers

### 4.1 `ci/drift_checker.py`

Responsibilities:

```text
detect cross-layer imports
detect multi-layer orchestration scripts
detect N3 -> N4 -> N5 -> N6 chains
detect legacy signal usage by delegating to signal rules
```

### 4.2 `ci/signal_guard.py`

Responsibilities:

```text
enforce ACTIVE signal whitelist
block B_BUY_30M_VOL
block S_SELL_30M_SHRINK
distinguish active paths from historical evidence paths
```

### 4.3 `ci/layer_boundary_check.py`

Responsibilities:

```text
enforce N1-N5 layer separation
detect illegal imports between layer packages
detect direct higher-layer execution imports
detect lower-layer mutation patterns when visible statically
```

## 5. Mandatory CI Rules

A proposed change must be rejected if any of the following occurs:

```text
N1 imports N2-N5 logic.
N2 accesses runtime execution layers.
N3 contains orchestration logic or executes N4/N5/N6.
N4 performs action execution logic.
N5 performs trigger logic.
Any script executes multiple layers sequentially.
Legacy 30m signal types appear in an active decision path.
```

## 6. Pass Conditions

A change passes only when all are true:

```text
No illegal cross-layer import is detected.
No orchestration leakage is detected.
No active legacy signal is detected.
No architecture boundary violation is detected.
Every reported static checker exits cleanly.
Every exception is documented as historical / compatibility / rollback evidence.
```

## 7. Fail Conditions

A change fails if any checker reports:

```text
DRIFT_CROSS_LAYER_IMPORT
DRIFT_ORCHESTRATION_CHAIN
DRIFT_LEGACY_SIGNAL_ACTIVE_PATH
DRIFT_LAYER_BOUNDARY_VIOLATION
DRIFT_RUNTIME_EXECUTION_LEAK
DRIFT_UNCLASSIFIED_LAYER
```

Failures must include:

```text
file path
line number when available
rule id
short reason
suggested owner layer
```

## 8. Changed-File Enforcement

Recommended CI invocation:

```bash
python3 ci/layer_boundary_check.py --changed-files <files...>
python3 ci/signal_guard.py --changed-files <files...>
python3 ci/drift_checker.py --changed-files <files...>
```

The checkers are designed for static review. They do not import project runtime modules, connect to databases, execute workers, consume outbox, run migrations, or mutate files.

## 9. Baseline Handling

The repository may contain historical reports, rollback SQL, compatibility migrations, and preserved run evidence that mention legacy semantics.

Baseline rule:

```text
Historical evidence may be preserved.
New active decision paths may not reintroduce legacy behavior.
```

Historical path indicators:

```text
docs/*REPORT*
docs/*POST_REVIEW*
docs/*ROLLBACK*
docs/*HISTORICAL*
sql/*rollback*
sql/*compatibility*
```

Active path indicators:

```text
src/
scripts/run_*
scripts/*execute*
scripts/*worker*
sql/*schema*.sql
sql/*migration*.sql
tests/
configs/
```

## 10. No Runtime Side Effects

The Drift CI System must not:

```text
execute N1-N6 code
connect to PostgreSQL
read or write runtime tables
consume outbox
start workers
run rollback SQL
write generated artifacts
modify source files
```

## 11. Enforcement Coverage

The system covers:

```text
N1 -> N2-N5 import violations
N2 -> runtime execution layer access
N3 -> N4/N5/N6 orchestration
N4 -> N5 action behavior leakage
N5 -> N4 trigger behavior leakage
multi-layer execution scripts
legacy 30m signal reintroduction
active decision-path signal whitelist
```

## 12. Golden Rule

No change is accepted unless Drift CI passes before the change is merged or treated as final.
