# N2-R2 Overwrite Execute Report

Date: 2026-05-24T18:17:04
Layer: N2_condition
Mode: overwrite_execute
Status: passed

## Run

```text
new_active_run = condition_layer_20260522_to_20260525_20260524181321_execute
previous_active_run = condition_layer_20260522_to_20260525_20260524014029_execute
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
```

## Status Checks

```text
new_run_status = passed
old_run_status = superseded
active_passed_run_count = 1
P0/P1/P2 = 0/5/3
```

## Row Counts

| table | expected | actual | matched |
|---|---:|---:|---:|
| `stock_condition_basis` | 5504 | 5504 | true |
| `index_condition_basis` | 81 | 81 | true |
| `board_condition_basis` | 428 | 428 | true |
| `stock_condition_pool` | 4236 | 4236 | true |
| `index_condition_pool` | 18 | 18 | true |
| `board_condition_pool` | 258 | 258 | true |
| `stock_minute_target_scope` | 4236 | 4236 | true |
| `index_minute_target_scope` | 18 | 18 | true |
| `board_minute_target_scope` | 258 | 258 | true |


## Reference Period Validation

```text
up_sell_reference_period missing = 0
down_buy_reference_period missing = 0
clear_sell_ref_period missing = 0
clear_sell_ref_period = up_sell_reference_period mismatch = 0
invalid reference period = 0
```

Checked persisted columns in:

```text
stock_condition_basis
index_condition_basis
board_condition_basis
stock_condition_pool
```

## Fixed 9 Index Golden

```text
present = 9/9
matched = 9/9
```

| code | identity_key | name | matched | prev_up_str | prev_dn_str | buy_key | sell_key |
|---|---|---|---:|---|---|---|---|
| 000001 | index:SH:000001 | 上证指数 | true | YQM-- | ---w- | BUY:W,D | SELL:Y,Q,M,D |
| 000016 | index:SH:000016 | 上证50 | true | ----- | ---w- | BUY:Y,Q,M,W,D | SELL:Y,Q,M,D |
| 000300 | index:SH:000300 | 沪深300 | true | YQM-- | ---w- | BUY:W,D | SELL:Y,Q,M,D |
| 000688 | index:SH:000688 | 科创50 | true | YQMW- | ----- | BUY:D | SELL:Y,Q,M,W,D |
| 000852 | index:SH:000852 | 中证1000 | true | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D |
| 000905 | index:SH:000905 | 中证500 | true | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D |
| 399001 | index:SZ:399001 | 深证成指 | true | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D |
| 399006 | index:SZ:399006 | 创业板指 | true | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D |
| 399303 | index:SZ:399303 | 国证2000 | true | YQM-- | ----- | BUY:W,D | SELL:Y,Q,M,W,D |


## common_event_outbox

```text
before_row_count = 26652
after_row_count = 26652
unchanged = true
written_by_this_execute = false
```

## Artifacts

```text
pre_execute_snapshot = backups/N2_R2_overwrite_before_snapshot_20260524181105.json
post_execute_snapshot = /Users/chuanfuchen/Documents/A股监控系统v3/backups/N2_R2_overwrite_after_snapshot_20260524181703.json
json_report = /Users/chuanfuchen/Documents/A股监控系统v3/docs/N2_R2_overwrite_execute_report.json
rollback_sql = /Users/chuanfuchen/Documents/A股监控系统v3/sql/N2_R2_overwrite_rollback.sql
raw_execute_report = /Users/chuanfuchen/Documents/A股监控系统v3/tmp/N2_R2_overwrite_execute_raw.json
```


## Validation

```text
python3 -m compileall scripts src tests: passed
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_condition*.py': passed, 61 tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_scope_policy.py': passed, 10 tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_minute_target_scope.py': passed, 9 tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n2_web_policy.py': passed, 23 tests
git diff --check: passed
```

Full unittest is not used as this N2 gate because `tests/test_action_event_contract.py` currently fails in N5 scope and this run must not modify N5.

## Boundary

```text
old_system_touched: no
external_market_api_called: no
minute_k_pulled: no
worker_started: no
entered_N3_N4_N5_N6: no
n1_source_version_modified: no
trade_calendar_repaired: no
common_event_outbox_written: no
migration_performed: no
condition_business_rows_written: yes
```

## Next Step

Stop here. Do not enter N3 unless the user explicitly switches layer_role to N3_market_data.
