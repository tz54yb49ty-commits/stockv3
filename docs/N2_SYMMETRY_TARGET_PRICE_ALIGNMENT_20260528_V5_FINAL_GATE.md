# N2 Symmetry Target Price Alignment v5 Final Gate

source_trade_date = 20260528
for_trade_date = 20260529
target_run_id = condition_layer_20260528_source_20260528_v5
previous_active_run_id = condition_layer_20260528_source_20260528_v4
overwrite_semantics = lineage_supersede_only
n3_lineage_auto_switch = false
writes_performed = false


gate_result = PASS
allow_enter_execute_user_confirmation_point = True
blocked_reasons = []

## Execute Risk

medium-low

## Rollback Risk

low before downstream consumption; guarded and blocked after N3/N4/N5/N6 refs exist

## Execute Command Candidate

```bash
PYTHONPATH=src python3 scripts/run_condition_layer_execute.py --source-trade-date 20260528 --policy configs/n2_policy/default_policy_draft.json --run-id condition_layer_20260528_source_20260528_v5 --execute --user-confirmed --overwrite --operator codex --confirmation-note N2-symmetry-target-price-alignment-v5-active-supersede --report-path docs/N2_symmetry_target_price_alignment_20260528_v5_execute_report.json
```

## Before Checklist

- Confirm target_run_baseline_total remains 0
- Confirm current active remains condition_layer_20260528_source_20260528_v4 passed_active
- Confirm downstream refs for v5 remain 0
- Use --execute --user-confirmed --overwrite and fixed run_id v5
- Do not auto rebuild N3 after execute

## After Checklist

- v5.status = passed_active
- v4.status = superseded
- 000027 buy_target_price/reference_target_price = 8.42
- condition_basis/pool/scope/display row counts match expected_rows_with_display
- common_event_outbox/inbox/checkpoint delta = 0
- N3/N4/N5/N6 refs for v5 remain 0 until separately authorized
- rollback_safe = true if no downstream refs

## Boundary

- no N2 execute in this gate
- no condition_* business writes in this gate
- no market data pull
- no N3/N4/N5/N6 execute
- no worker
- no old system / real trading
