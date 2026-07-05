# N2 Trigger Baseline Semantic Repair Preflight

Gate: `N2_TRIGGER_BASELINE_SEMANTIC_REPAIR_PREFLIGHT_GATE`

Layer role: `N2_condition`

Preflight result: `PASS`

Current live semantic status: `SEMANTIC_FAIL`

This preflight PASS only means the repair contract is ready for implementation. It does not mean the current live N2/N4 context is already fixed.

## Boundary Proof

```text
execute_n2=false
write_database=false
rollback=false
enter_n3=false
enter_n4=false
enter_n5=false
enter_n6=false
consume_outbox=false
start_worker=false
pull_market_data=false
```

## Sample Validation

### 002399.SZ

```text
asset_kind=stock
identity_key=stock:SZ:002399
period=D
source_trade_date=20260604
current seed open/close=9.66/9.45

current legacy previous_entity_high/low=9.79/9.67
legacy period_key_previous=20260603

expected trigger_previous_open=9.79
expected trigger_previous_close=9.67
expected trigger_previous_entity_high=9.79
expected trigger_previous_entity_low=9.67
expected current_seed_entity_high=9.66
expected current_seed_entity_low=9.45
expected baseline_source_trade_date=20260604
```

### 399006

```text
asset_kind=index
identity_key=index:SZ:399006
period=D
source_trade_date=20260604
current seed open/close=4088.88/4072.55

current legacy previous_entity_high/low=4122.99/4089.02
legacy period_key_previous=20260603

expected trigger_previous_entity_high=4122.99
expected trigger_previous_entity_low=4089.02
expected current_seed_entity_high=4088.88
expected current_seed_entity_low=4072.55
expected baseline_source_trade_date=20260604
```

### 881078 Board W

```text
asset_kind=board
identity_key=board:TDX:881078
period=W
current seed open/close=706.84/712.3

expected trigger_previous_entity_low=632.78
expected trigger_previous_entity_high=696.8
expected current_seed_entity_low=706.84
expected current_seed_entity_high=712.3
```

### Board Contract

Board trigger baseline follows the same mapping as stock/index:

```text
trigger fields come from previous complete period entity fields
current_* seed fields are trace only
```

## Required Tests

```text
stock sample: 002399.SZ expected trigger high/low = 9.66/9.45
index sample: 399006 expected trigger high/low = 4088.88/4072.55
board sample: same mapping as stock/index
legacy previous_* not allowed as N4 trigger baseline
baseline_source_trade_date must equal source_trade_date
trigger_previous_amount_baseline must be present
```

## Remaining Blockers

```text
N2 code has not yet populated trigger_previous_* fields.
N4 context reader/localizer still needs verification or N4 handoff after N2 implementation.
Current live N2/N4 context remains SEMANTIC_FAIL until a later implementation and execute path is explicitly approved.
```

## Next Gate

```text
N2_TRIGGER_BASELINE_SEMANTIC_REPAIR_IMPLEMENTATION_GATE
```
