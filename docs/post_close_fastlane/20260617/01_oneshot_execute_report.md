# Post-Close N1-N2-N3A1 One-Shot Report

- result: `EXECUTE_PASS`
- source_trade_date: `20260616`
- for_trade_date: `20260617`
- failed_step_id: `None`

## Steps
- `n1_source_facts` returncode=`0`
- `n1_stock_financial_canonical_source_bundle` returncode=`0`
- `n1_stock_financial_canonical_metrics` returncode=`0`
- `n2_condition` returncode=`0`
- `n3_subscription` returncode=`0`
- `n3_a0_preload_dry_run` returncode=`0`
- `n3_a1_contract` returncode=`0`
- `n3_a1_preload` returncode=`0`

## Forbidden Scope

- n3_b_c_b2_executed: `False`
- n4_n5_n6_entered: `False`
- outbox_inbox_checkpoint_consumed_or_updated: `False`
- worker_started: `False`
- delivery_push_voice_mobile: `False`
- sim_position_pnl_real_trade: `False`
- proposal_order_trade: `False`
- old_system_touched: `False`
