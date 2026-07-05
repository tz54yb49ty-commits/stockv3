# V3 20260612 Realtime Virtual Metric Writer Payload

- result: `SOURCE_PAYLOAD_PREFLIGHT_PASS`
- target_run_id: `action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1`
- candidate_count: `100`
- signal_distribution: `B_BUY=76 / S_SELL=24`
- asset_distribution: `stock=62 / index=0 / board=38`
- source_record_code_count: `45`
- source_record_total_rows: `15508`
- D/W/M/Q/Y context coverage: `complete`

## Source Boundary

Old system SQLite was opened read-only with `mode=ro` and only `action_fact_cache` / `minute_kline` were queried under runtime_control authorization. The old system rows are recorded as diagnostic candidate/source-minute inputs for this payload only and are not registered as V3 active lineage.

## Payload Paths

- JSON: `docs/V3_20260612_realtime_virtual_metric_writer_payload.json`
- Markdown: `docs/V3_20260612_realtime_virtual_metric_writer_payload.md`
