# N3 B2 Stock/Index Minute Lineage Expansion Dry-Run

- result: PASS
- expansion_run_id: `market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`
- source_condition_run_id: `condition_layer_20260604_source_20260604_v1`
- source_subscription_run_id: `market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- source B1 snapshot: `realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- source C1 minute: `today_minute_bar_1m_20260605_until_1127__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- candidate/subscription/pull_plan: 6696/3350/4
- expansion objects: stock=1668 index=7 board=0 total=1675
- current minute rows: stock=195156 index=819 total=195975
- previous-day minute rows: stock=400320 index=1680 total=402000
- P0/P1/P2: 0/2/0

## Residuals

- stock/index completion-only rows remain visible: stock=136 index=2
- board 14:59 remains quality-visible not_ready=428; this gate does not silently fallback or downgrade it.

## Boundary

- no database writes
- no market data pull
- no outbox/inbox/checkpoint writes or consumption
- no N4/N5/N6
- no worker / old system / real trading
