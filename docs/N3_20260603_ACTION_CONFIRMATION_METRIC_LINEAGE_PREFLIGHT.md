# N3 20260603 Action-Confirmation Metric Lineage Preflight

- result: `PREFLIGHT_PASS`
- blocked: `False`
- planned rows stock/index/board/total: `640/34/148/822`
- N4 coverage: `863/863`
- metric_ready/not_ready: `822/0`
- scoped baseline run/quality/metric/outbox/inbox/checkpoint: `{'common_market_data_run': 0, 'common_market_data_quality_item': 0, 'stock_metric': 0, 'index_metric': 0, 'board_metric': 0, 'outbox_refs': 0, 'inbox_refs': 0, 'checkpoint_refs': 0}`
- P0/P1/P2: `0/2/0`

Allowed future writes are limited to common_market_data_run, common_market_data_quality_item, and stock/index/board_action_confirmation_projection_metric. This preflight does not authorize execute.
