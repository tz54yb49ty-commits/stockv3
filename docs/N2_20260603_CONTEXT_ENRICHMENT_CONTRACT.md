# N2 Context Enrichment Contract

- contract_version: N2-context-enrichment-v1
- downstream_consumer: N4_trigger
- physical_columns_required: False
- schema_migration_required: False
- n4_can_recompute_context: False
- JSON extension paths:
  - period_trigger_baseline_json.context_enrichment
  - period_trigger_baseline_json.periods.*.previous_transition
  - period_trigger_baseline_json.periods.*.previous_amount_baseline
  - period_trigger_baseline_json.periods.*.period_baseline_ready
  - period_trigger_baseline_json.periods.*.baseline_source_trade_date
  - period_trigger_baseline_json.periods.*.source_version
  - period_trigger_baseline_json.periods.*.freshness_status
  - raw_json.trigger_amount_chain_baseline_json
  - raw_json.FULL_prerequisite_trace_json
  - raw_json.HINT_prerequisite_trace_json

FULL policy: BUY:FULL / SELL:FULL remain trace-only and blocked for N4 v4 execute matcher.
HINT policy: BUY_HINT / SELL_HINT keep N2 prerequisite trace; N4 must confirm standardized N3 projection.
