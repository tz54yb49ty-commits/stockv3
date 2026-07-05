# V3 Realtime Engine Production Run Once

- result: `BLOCKED`
- reason: `None`
- blocked_reason: `n6_user_projection_failed`
- execution_mode: `execute`
- for_trade_date: `None`

## Child Command Plan

- N3_N4_N5_DYNAMIC_CHAIN: argv_list=True execute=True user_confirmed=True
- N6_USER_PROJECTION: argv_list=True execute=True user_confirmed=True

## Executed Steps

- N3_N4_N5_DYNAMIC_CHAIN: returncode=0
- N6_USER_PROJECTION: returncode=2

## Forbidden Scope

- n6_projection_only: `True`
- voice_mobile_sim_trade_touched: `False`
- proposal_order_trade_sim_position_pnl_real_trade: `False`
- old_system_touched: `False`
- long_running_worker_started: `False`
- scheduler_installed_or_enabled: `False`
- rollback_executed: `False`
- shell_string_used: `False`
- non_authorized_outbox_inbox_checkpoint_consumed_or_updated: `False`
