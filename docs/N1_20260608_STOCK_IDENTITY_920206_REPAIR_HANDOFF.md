# N1 20260608 Stock Identity 920206 Repair Handoff

Result: `SUPERSEDED`

Decision: `SUPERSEDED_BY_SMALL_MISSING_STOCK_IDENTITY_SKIP_POLICY`

The 20260608 source facts runner will not write `stock_identity`. The missing identity is now handled by the explicit stock-only skip policy for this source facts gate.

## Missing Identity

```json
{
  "ts_code": "920206.BJ",
  "code": "920206",
  "exchange": "BJ",
  "canonical_identity_key": "stock:BJ:920206",
  "observed_in": [
    "Tushare daily 20260608",
    "Tushare daily_basic 20260608"
  ],
  "current_active_stock_identity_scope": "A_STOCK:20260605 -> stock_identity_20260605_v1"
}
```

## Superseded Repair Scope

```json
{
  "allowed_tables": [
    "stock_identity",
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version"
  ],
  "forbidden_tables": [
    "stock_daily_bar_fact",
    "index_daily_bar_fact",
    "board_daily_bar_fact",
    "stock_daily_basic",
    "stock_financial_metrics_fact",
    "index_membership_fact",
    "board_membership_fact",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "N2/N3/N4/N5/N6"
  ]
}
```

## Next Gate

`N1_20260608_SOURCE_FACTS_EXECUTE_FINAL_GATE_REVIEW`
