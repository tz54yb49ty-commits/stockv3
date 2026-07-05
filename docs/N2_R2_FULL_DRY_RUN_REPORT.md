# N2-R2 Full Dry-Run Report

Date: 2026-05-24T17:59:04
Layer: N2_condition
Mode: full_dry_run
Status: passed

## Date Context

```text
source_trade_date = 20260522
for_trade_date = 20260525
prev_trade_date = 20260522
active index_daily = index_daily_20260522_v4
```

## Row Counts

| stage | stock | index | board |
|---|---:|---:|---:|
| condition_basis | 5504 | 81 | 428 |
| condition_pool | 4236 | 18 | 258 |
| minute_target_scope | 4236 | 18 | 258 |
| minute_target_scope objects | 2052 | 9 | 127 |

## Quality

| stage | P0 | P1 | P2 |
|---|---:|---:|---:|
| condition_basis | 0 | 3 | 1 |
| condition_pool | 0 | 1 | 1 |
| minute_target_scope | 0 | 1 | 1 |
| combined | 0 | 5 | 3 |

P1/P2 are retained as warnings only. No P0 blocker was found.

## N2-R2 Reference Period Acceptance

```text
up_sell_reference_period missing = 0
down_buy_reference_period missing = 0
clear_sell_ref_period missing = 0
clear_sell_ref_period = up_sell_reference_period mismatch = 0
invalid reference period = 0
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

## Scope Contract

```text
scope_source stock = {'condition_pool': 4236}
scope_source index = {'condition_pool': 18}
scope_source board = {'condition_pool': 258}
previous_day_minute_date mismatch = {'stock': 0, 'index': 0, 'board': 0}
```

## Common Event Outbox

```text
baseline row_count after 011 = 26652
current row_count = 26652
row_count unchanged = true
written_by_this_full_dry_run = false
```

## Validation

```text
python3 -m compileall scripts src tests: passed
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_condition*.py': passed, 61 tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_scope_policy.py': passed, 10 tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_minute_target_scope.py': passed, 9 tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n2_web_policy.py': passed, 23 tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_schema_readiness.py': passed, 7 tests
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
active_condition_run_overwritten: no
condition_business_rows_written: no
common_event_outbox_written: no
```

## Next Step

Stop here. Do not execute N2-R2 overwrite unless the user explicitly confirms it.
