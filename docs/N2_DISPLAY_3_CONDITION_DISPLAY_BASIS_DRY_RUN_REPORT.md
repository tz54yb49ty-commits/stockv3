# N2-Display-3 Condition Display Basis Dry-run Report

layer_role = N2_condition
status = DRY_RUN_PASS

## Run

```text
run_id = condition_layer_20260522_to_20260525_20260525003855_execute
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
writes_performed = false
display_basis_written = false
overwrite_performed = false
downstream_layers_touched = false
```

## Preview Row Counts

| Domain | Display table | Rows | Objects |
|---|---|---:|---:|
| stock | stock_condition_display_basis | 5504 | 5504 |
| index | index_condition_display_basis | 81 | 81 |
| board | board_condition_display_basis | 428 | 428 |

## Validation

| Domain | Duplicate keys | Missing basis trace | Invalid condition keys | Invalid signal types | Invalid baseline shape | Reference mismatches | Invalid reference period | Forbidden fields | Empty scope trace |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stock | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3452 |
| index | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 72 |
| board | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 301 |

## Display Table Row Counts

| Table | Before | After |
|---|---:|---:|
| stock_condition_display_basis | 0 | 0 |
| index_condition_display_basis | 0 | 0 |
| board_condition_display_basis | 0 | 0 |

## Quality

```text
p0_count = 0
p1_count = 0
p2_count = 0
can_enter_n2_full_dry_run = true
```

## Samples

### stock

```json
[
  {
    "identity_key": "stock:BJ:920000",
    "code": "920000",
    "name": "安徽凤凰",
    "selected_condition_keys": [],
    "selected_signal_types": [],
    "source_condition_basis_ids_json": [
      27521
    ],
    "source_condition_pool_ids_json": [],
    "source_minute_target_scope_ids_json": [],
    "display_scope_reason": "basis_only_no_condition_pool_or_scope_rows",
    "buy_target_price": null,
    "sell_target_price": "9.59",
    "up_sell_reference_period": "D",
    "down_buy_reference_period": "M",
    "quality_status": "passed"
  },
  {
    "identity_key": "stock:BJ:920001",
    "code": "920001",
    "name": "纬达光电",
    "selected_condition_keys": [],
    "selected_signal_types": [],
    "source_condition_basis_ids_json": [
      27522
    ],
    "source_condition_pool_ids_json": [],
    "source_minute_target_scope_ids_json": [],
    "display_scope_reason": "basis_only_no_condition_pool_or_scope_rows",
    "buy_target_price": "22.74",
    "sell_target_price": null,
    "up_sell_reference_period": "D",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  },
  {
    "identity_key": "stock:BJ:920002",
    "code": "920002",
    "name": "万达轴承",
    "selected_condition_keys": [],
    "selected_signal_types": [],
    "source_condition_basis_ids_json": [
      27523
    ],
    "source_condition_pool_ids_json": [],
    "source_minute_target_scope_ids_json": [],
    "display_scope_reason": "basis_only_no_condition_pool_or_scope_rows",
    "buy_target_price": "111.72",
    "sell_target_price": "82.39",
    "up_sell_reference_period": "W",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  }
]
```

### index

```json
[
  {
    "identity_key": "index:SH:000001",
    "code": "000001",
    "name": "上证指数",
    "selected_condition_keys": [
      "BUY:W,D",
      "SELL:Y,Q,M,D"
    ],
    "selected_signal_types": [
      "B_BUY",
      "B_BUY_30M_VOL",
      "S_SELL",
      "S_SELL_30M_SHRINK"
    ],
    "source_condition_basis_ids_json": [
      404
    ],
    "source_condition_pool_ids_json": [
      354,
      355
    ],
    "source_minute_target_scope_ids_json": [
      99,
      100
    ],
    "display_scope_reason": "source_minute_target_scope_ids_present",
    "buy_target_price": "4541.46",
    "sell_target_price": "3981.12",
    "up_sell_reference_period": "W",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  },
  {
    "identity_key": "index:SH:000009",
    "code": "000009",
    "name": "上证380",
    "selected_condition_keys": [],
    "selected_signal_types": [],
    "source_condition_basis_ids_json": [
      405
    ],
    "source_condition_pool_ids_json": [],
    "source_minute_target_scope_ids_json": [],
    "display_scope_reason": "basis_only_no_condition_pool_or_scope_rows",
    "buy_target_price": "8363.63",
    "sell_target_price": null,
    "up_sell_reference_period": "W",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  },
  {
    "identity_key": "index:SH:000010",
    "code": "000010",
    "name": "上证180",
    "selected_condition_keys": [],
    "selected_signal_types": [],
    "source_condition_basis_ids_json": [
      406
    ],
    "source_condition_pool_ids_json": [],
    "source_minute_target_scope_ids_json": [],
    "display_scope_reason": "basis_only_no_condition_pool_or_scope_rows",
    "buy_target_price": "10715.442",
    "sell_target_price": "9817.675",
    "up_sell_reference_period": "W",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  }
]
```

### board

```json
[
  {
    "identity_key": "board:TDX:880201",
    "code": "880201",
    "name": "黑龙江",
    "selected_condition_keys": [],
    "selected_signal_types": [],
    "source_condition_basis_ids_json": [
      2141
    ],
    "source_condition_pool_ids_json": [],
    "source_minute_target_scope_ids_json": [],
    "display_scope_reason": "basis_only_no_condition_pool_or_scope_rows",
    "buy_target_price": "1075.22",
    "sell_target_price": "771.85",
    "up_sell_reference_period": "Q",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  },
  {
    "identity_key": "board:TDX:880202",
    "code": "880202",
    "name": "新疆板块",
    "selected_condition_keys": [],
    "selected_signal_types": [],
    "source_condition_basis_ids_json": [
      2142
    ],
    "source_condition_pool_ids_json": [],
    "source_minute_target_scope_ids_json": [],
    "display_scope_reason": "basis_only_no_condition_pool_or_scope_rows",
    "buy_target_price": null,
    "sell_target_price": "1045.17",
    "up_sell_reference_period": "D",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  },
  {
    "identity_key": "board:TDX:880203",
    "code": "880203",
    "name": "吉林板块",
    "selected_condition_keys": [],
    "selected_signal_types": [],
    "source_condition_basis_ids_json": [
      2143
    ],
    "source_condition_pool_ids_json": [],
    "source_minute_target_scope_ids_json": [],
    "display_scope_reason": "basis_only_no_condition_pool_or_scope_rows",
    "buy_target_price": null,
    "sell_target_price": "859.65",
    "up_sell_reference_period": "D",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  }
]
```
