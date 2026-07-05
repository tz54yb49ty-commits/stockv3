# N3-B1 BoardMarketDataAdapter Implementation

## Scope

```text
layer_role=N3_market_data
stage=N3-B1 BoardMarketDataAdapter implementation
business_data_written=false
realtime_snapshot_written=false
event_outbox_written=false
worker_started=false
downstream_layers_touched=false
```

This implementation only changes the N3-B1 realtime snapshot adapter routing and tests. It does not execute B1 and does not write database rows.

## Root Cause Fixed

The previous generic adapter used:

```python
client.quotes(symbol=code)
```

For `board:TDX:881xxx`, this returns an empty DataFrame. Probe evidence showed that TDX industry board codes are available through the index-like path:

```python
client.index(symbol=code, frequency=9, start=0, offset=5)
```

## Implementation

New adapter:

```text
BoardMarketDataAdapter
```

Routing:

```text
asset_kind=board
exchange=TDX
code starts with 881
  -> BoardMarketDataAdapter

stock/index and non-881 board-like rows
  -> existing MootdxRealtimeSnapshotAdapter
```

The default B1 execute path now uses:

```text
AssetRoutingRealtimeSnapshotAdapter
```

Injected adapters in tests or future dry-run harnesses still bypass this default route.

## Board Field Mapping

```text
open          <- tail row open
high          <- tail row high
low           <- tail row low
close         <- tail row close
current_price <- tail row close
pre_close     <- previous returned row close
volume        <- tail row volume, fallback vol
amount        <- tail row amount
snapshot_time <- tail row datetime
```

The adapter requires the selected tail row date to equal `for_trade_date`. If the returned frame is empty, the row is missing, or the tail row date does not match `for_trade_date`, the adapter returns `None`; B1 then writes `MarketDataMissing` quality evidence instead of writing a false-success snapshot.

## Raw JSON Trace

Board snapshots preserve:

```text
adapter_name=BoardMarketDataAdapter
source_path=std.index
source_version=mootdx.quotes.board_index_snapshot.v1
raw_payload.up_count
raw_payload.down_count
```

The N3 event/fact path still uses the existing `source_adapter` value from the reviewed B1 contract.

## Tests

Added coverage:

```text
board successful mapping
board empty frame -> missing
board trade_date mismatch -> missing
stock/index continue through default adapter
board:TDX:881xxx routes to board adapter
```

## Rerun Gate

This implementation allows returning to:

```text
N3-B1 readiness / execute contract refresh
```

It does not itself authorize B1 execute. B1 can only rerun after a fresh readiness/contract check and explicit user confirmation.
