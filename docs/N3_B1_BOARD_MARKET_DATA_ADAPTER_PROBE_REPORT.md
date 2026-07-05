# N3-B1 BoardMarketDataAdapter Probe Report

## Scope

```text
layer_role=N3_market_data
probe=BoardMarketDataAdapter
source_run_id=market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
business_data_written=false
realtime_snapshot_written=false
event_outbox_written=false
worker_started=false
downstream_layers_touched=false
```

This probe only read board realtime snapshot subscriptions and called small-sample mootdx/TDX quote APIs.

## Samples

```text
board:TDX:881002 煤炭开采
board:TDX:881005 焦炭加工
board:TDX:881007 油气开采
board:TDX:881008 油服工程
board:TDX:881011 石油化工
```

## Probe Result

```text
PROBE_PASS
```

Usable path:

```python
Quotes.factory(market="std").index(symbol=code, frequency=9, start=0, offset=5)
```

Equivalent usable path:

```python
Quotes.factory(market="std").index_bars(symbol=code, frequency=9, start=0, offset=5)
```

Not usable paths:

```text
std.quotes(symbol=881xxx): empty DataFrame
std.quotes(symbol=[881xxx...]): empty DataFrame
std.bars(symbol=881xxx, frequency=9): empty DataFrame
std.minute(symbol=881xxx): validation error
ext.quote(market=31/47/48/27/1, symbol=881002): one row but all price fields are zero
```

## Returned Fields

`std.index` and `std.index_bars` returned mappable daily index rows for all sampled `881xxx` board codes.

Returned columns:

```text
open
close
high
low
vol
amount
year
month
day
hour
minute
datetime
up_count
down_count
volume
```

The tail row for each sample was `2026-05-25 15:00`, matching `for_trade_date=20260525`.

## Field Mapping

Recommended mapping into `board_realtime_daily_snapshot`:

```text
open          <- open
high          <- high
low           <- low
close         <- close
current_price <- close
pre_close     <- previous returned row close, if available
volume        <- volume if present else vol
amount        <- amount
snapshot_time <- tail row datetime
raw_json      <- full row plus adapter metadata, including up_count/down_count
```

## Root Cause

The current generic realtime snapshot adapter uses:

```python
client.quotes(symbol=code)
```

That works for stock/index subscriptions but returns an empty DataFrame for TDX board codes `881xxx`. TDX board sector codes must be treated as index-like quote objects and fetched through `std.index` or `std.index_bars`.

## Recommendation

Add a dedicated `BoardMarketDataAdapter` in N3-B1 implementation:

```text
asset_kind=board
source_adapter=BoardMarketDataAdapter
fetch path=std.index(symbol=code, frequency=9, start=0, offset=5)
select row=tail row whose date equals for_trade_date
quality rule=if no for_trade_date row, emit MarketDataMissing
```

Do not use ext quote for board snapshot because the sampled rows were all zero and mootdx warns that the ext market quote API is currently invalid.

## Risks

```text
1. std.index returns daily index/K-line shaped data, not quote-book data.
2. snapshot_time is the returned row datetime, commonly 15:00 for the current trade date.
3. B1 should require tail-row trade date to equal for_trade_date before writing board snapshots.
4. If board needs pre_close, derive it from the previous returned row close or existing previous-day fact, not from ext quote zero rows.
```

## Next Step

Allow entering:

```text
N3-B1 BoardMarketDataAdapter implementation
```

Implementation should update the realtime snapshot adapter routing so only `asset_kind=board` uses `BoardMarketDataAdapter`; stock/index behavior should remain unchanged.
