# N3 C1 Full-Context Expansion Subscription Dry-Run

- result: PASS
- market_data_run_id: `market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1`
- source_condition_run_id: `condition_layer_20260602_source_20260602_v1`
- current_c1_run_id: `today_minute_bar_1m_20260603_until_1500__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- candidate rows: 4391
- subscription rows: 2197
- pull_plan rows: 3
- objects: {'stock': 1722, 'index': 81, 'board': 394}
- expected minute rows: {'stock': 413280, 'index': 19440, 'board': 94560} total=527280
- P0/P1/P2: 0/0/0

## Boundary

- no database writes
- no market data pull
- no outbox/inbox/checkpoint writes
- no N4/N5/N6
- no worker
