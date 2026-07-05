# N4 Context Refresh Execute Preflight

Result: `PREFLIGHT_BLOCKED`

The data and reader preflight passed, but direct execute is blocked because the target context run already exists.

## Data Reader Preflight

```text
candidate rows = 5118
stock/index/board = 4186/20/912
P0/P1/P2 = 0/0/0
trigger_previous_entity_high/low missing = 0
trigger_previous_amount_baseline missing = 0
baseline_source_trade_date mismatch = 0
legacy previous used as trigger baseline = 0
required_period_not_ready_rows = 0
```

## Target DB Baseline

Existing target context rows:

```text
common_trigger_run = 1
stock_trigger_context_snapshot = 4186
index_trigger_context_snapshot = 20
board_trigger_context_snapshot = 912
```

Target trigger execute refs remain clean:

```text
common_trigger_run/state/match/outbox = 0/0/0/0
```

Context downstream refs remain clean:

```text
common_trigger_state/match/outbox = 0/0/0
```

## Blocker

```text
P0 target_context_run_already_exists
```

The existing target context run must be removed by an approved N4-only context rollback, or the runner must be separately aligned for refresh-replace semantics, before direct context refresh execute can proceed.

## Rollback Static Expectations

```text
RAISE EXCEPTION before first DELETE = true
no UPDATE = true
no DROP/TRUNCATE/CASCADE = true
N4 context-only DELETE scope = true
N5/N6 guards = true
```

## Next Route

Not allowed:

```text
direct N4 context refresh execute final gate
N4 TriggerMatched execute
N5/N6
```

Allowed:

```text
runtime_control context-refresh replacement review
```
