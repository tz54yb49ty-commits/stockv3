# N3 B2 Realtime Projection 20260605 Live2 Execute Contract

Status: **CONTRACT_PASS**

Preflight expected result: **PREFLIGHT_PASS**

Allowed writes are limited to `common_market_data_run`, `common_market_data_quality_item`, and stock/index/board realtime projection metric tables. The contract remains fact-only: `writes_outbox=false`, `consumes_outbox=false`, and no N4/N5/N6 worker or downstream write is allowed.

Expected rows stock/index/board/total: 1952/9/428/2389.
Ready/not_ready: 969/1420.

Fact-only B1 trace compatibility is explicit. Missing `snapshot_event_id` is accepted only because snapshot fact trace fields are complete for all 2389 rows.
