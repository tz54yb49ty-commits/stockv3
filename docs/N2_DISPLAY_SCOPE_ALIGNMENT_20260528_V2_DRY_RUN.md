# N2-Display-3 Condition Display Basis Dry-run Report

layer_role = N2_condition
status = DRY_RUN_PASS

## Run

```text
run_id = condition_layer_20260528_source_20260528_v2
source_trade_date = 20260528
for_trade_date = 20260529
prev_trade_date = 20260528
writes_performed = false
display_basis_written = false
overwrite_performed = false
downstream_layers_touched = false
```

## Preview Row Counts

| Domain | Display table | Rows | Objects |
|---|---|---:|---:|
| stock | stock_condition_display_basis | 2021 | 2021 |
| index | index_condition_display_basis | 9 | 9 |
| board | board_condition_display_basis | 127 | 127 |

## Validation

| Domain | Duplicate keys | Missing basis trace | Invalid condition keys | Invalid signal types | Invalid baseline shape | Reference mismatches | Invalid reference period | Forbidden fields | Empty scope trace |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stock | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| index | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| board | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Display Table Row Counts

| Table | Before | After |
|---|---:|---:|
| stock_condition_display_basis | 38536 | 38536 |
| index_condition_display_basis | 505 | 505 |
| board_condition_display_basis | 2996 | 2996 |

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
    "identity_key": "stock:BJ:920045",
    "code": "920045",
    "name": "蘅东光",
    "selected_condition_keys": [
      "BUY:Y,M,D",
      "SELL:Y,Q,M,W,D"
    ],
    "selected_signal_types": [
      "BUY",
      "SELL"
    ],
    "source_condition_basis_ids_json": [
      66096
    ],
    "source_condition_pool_ids_json": [
      70278,
      70279
    ],
    "source_minute_target_scope_ids_json": [
      57470,
      57471
    ],
    "display_scope_reason": "source_minute_target_scope_ids_present",
    "buy_target_price": "778.78",
    "sell_target_price": null,
    "up_sell_reference_period": "D",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  },
  {
    "identity_key": "stock:BJ:920068",
    "code": "920068",
    "name": "天工股份",
    "selected_condition_keys": [
      "BUY:Y,Q,M,W,D",
      "SELL:D"
    ],
    "selected_signal_types": [
      "BUY",
      "SELL"
    ],
    "source_condition_basis_ids_json": [
      66108
    ],
    "source_condition_pool_ids_json": [
      70280,
      70281
    ],
    "source_minute_target_scope_ids_json": [
      57472,
      57473
    ],
    "display_scope_reason": "source_minute_target_scope_ids_present",
    "buy_target_price": null,
    "sell_target_price": "10.12",
    "up_sell_reference_period": "D",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  },
  {
    "identity_key": "stock:BJ:920116",
    "code": "920116",
    "name": "星图测控",
    "selected_condition_keys": [
      "BUY:Y,Q,M,W,D",
      "SELL:Y,M,D"
    ],
    "selected_signal_types": [
      "BUY",
      "SELL"
    ],
    "source_condition_basis_ids_json": [
      66133
    ],
    "source_condition_pool_ids_json": [
      70282,
      70283
    ],
    "source_minute_target_scope_ids_json": [
      57474,
      57475
    ],
    "display_scope_reason": "source_minute_target_scope_ids_present",
    "buy_target_price": null,
    "sell_target_price": "57.96",
    "up_sell_reference_period": "D",
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
      "BUY:M,W,D",
      "SELL:Y,Q,M,W,D"
    ],
    "selected_signal_types": [
      "BUY",
      "SELL"
    ],
    "source_condition_basis_ids_json": [
      909
    ],
    "source_condition_pool_ids_json": [
      490,
      491
    ],
    "source_minute_target_scope_ids_json": [
      235,
      236
    ],
    "display_scope_reason": "source_minute_target_scope_ids_present",
    "buy_target_price": "4541.46",
    "sell_target_price": null,
    "up_sell_reference_period": "M",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  },
  {
    "identity_key": "index:SH:000016",
    "code": "000016",
    "name": "上证50",
    "selected_condition_keys": [
      "BUY:Y,Q,M,W,D",
      "SELL:Y,Q,M,W"
    ],
    "selected_signal_types": [
      "BUY",
      "SELL"
    ],
    "source_condition_basis_ids_json": [
      913
    ],
    "source_condition_pool_ids_json": [
      492,
      493
    ],
    "source_minute_target_scope_ids_json": [
      237,
      238
    ],
    "display_scope_reason": "source_minute_target_scope_ids_present",
    "buy_target_price": null,
    "sell_target_price": null,
    "up_sell_reference_period": "D",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  },
  {
    "identity_key": "index:SH:000300",
    "code": "000300",
    "name": "沪深300",
    "selected_condition_keys": [
      "BUY:D",
      "SELL:Y,Q,M,W,D"
    ],
    "selected_signal_types": [
      "BUY",
      "SELL"
    ],
    "source_condition_basis_ids_json": [
      918
    ],
    "source_condition_pool_ids_json": [
      494,
      495
    ],
    "source_minute_target_scope_ids_json": [
      239,
      240
    ],
    "display_scope_reason": "source_minute_target_scope_ids_present",
    "buy_target_price": "5550.44",
    "sell_target_price": null,
    "up_sell_reference_period": "D",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  }
]
```

### board

```json
[
  {
    "identity_key": "board:TDX:881002",
    "code": "881002",
    "name": "煤炭开采",
    "selected_condition_keys": [
      "BUY:Q,M",
      "SELL:Y,Q,M,W,D"
    ],
    "selected_signal_types": [
      "BUY",
      "SELL"
    ],
    "source_condition_basis_ids_json": [
      5438
    ],
    "source_condition_pool_ids_json": [
      4668,
      4669
    ],
    "source_minute_target_scope_ids_json": [
      3347,
      3348
    ],
    "display_scope_reason": "source_minute_target_scope_ids_present",
    "buy_target_price": "2996.23",
    "sell_target_price": null,
    "up_sell_reference_period": "M",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  },
  {
    "identity_key": "board:TDX:881005",
    "code": "881005",
    "name": "焦炭加工",
    "selected_condition_keys": [
      "BUY:Y,Q,M,W",
      "SELL:Y,W,D"
    ],
    "selected_signal_types": [
      "BUY",
      "SELL"
    ],
    "source_condition_basis_ids_json": [
      5439
    ],
    "source_condition_pool_ids_json": [
      4670,
      4671
    ],
    "source_minute_target_scope_ids_json": [
      3349,
      3350
    ],
    "display_scope_reason": "source_minute_target_scope_ids_present",
    "buy_target_price": null,
    "sell_target_price": "370.16",
    "up_sell_reference_period": "D",
    "down_buy_reference_period": "W",
    "quality_status": "passed"
  },
  {
    "identity_key": "board:TDX:881007",
    "code": "881007",
    "name": "油气开采",
    "selected_condition_keys": [
      "BUY:Q,M,W,D",
      "SELL:Y,Q,D"
    ],
    "selected_signal_types": [
      "BUY",
      "SELL"
    ],
    "source_condition_basis_ids_json": [
      5440
    ],
    "source_condition_pool_ids_json": [
      4672,
      4673
    ],
    "source_minute_target_scope_ids_json": [
      3351,
      3352
    ],
    "display_scope_reason": "source_minute_target_scope_ids_present",
    "buy_target_price": "3790.84",
    "sell_target_price": "2391.11",
    "up_sell_reference_period": "Q",
    "down_buy_reference_period": "D",
    "quality_status": "passed"
  }
]
```
