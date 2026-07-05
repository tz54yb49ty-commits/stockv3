# N3 Intraday B1/C1/B2 Auto-Poll Activation Command Composition

Result: `COMPOSITION_PASS`

Layer role: `N3_market_data`

This gate designs the auto-poll command composition. It did not implement a wrapper, install or enable cron/launchd, execute supervisor, execute B1/C1/B2, write database rows, consume or update outbox/inbox/checkpoint, enter N4/N5/N6, start a worker, touch old-system paths, or touch trading paths.

## Current Blocker

`activation_has_dynamic_generation_step=false`

The current live activation command shape invokes the supervisor directly. That is not enough because each latest closed minute needs B1/C1/B2 child artifacts generated and statically verified before the supervisor can safely execute child runners.

## Recommended Composition

Use option A: a dedicated wrapper script:

`scripts/run_n3_intraday_b1_c1_b2_auto_poll_once.py`

This keeps the supervisor narrow: it remains the bounded B1 -> C1 -> B2 executor once artifacts exist. The wrapper becomes the only command that cron/launchd may call later. Its job is to calculate the latest closed minute, no-op when appropriate, generate and verify child artifacts, then invoke the supervisor bounded pass.

Option B, enhancing the supervisor to generate artifacts internally, is not recommended because it mixes artifact-generation side effects into the execution orchestrator and makes plan-only smoke less isolated.

## Activation Command Shape

```text
PYTHONPATH=src:scripts python3 scripts/run_n3_intraday_b1_c1_b2_auto_poll_once.py \
  --for-trade-date <for_trade_date> \
  --subscription-run-id <subscription_run_id> \
  --preload-run-id <preload_run_id> \
  --source-condition-run-id <source_condition_run_id> \
  --docs-root docs \
  --sql-root sql \
  --json-report-path docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_<for_trade_date>.json \
  --markdown-report-path docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_<for_trade_date>.md \
  --execute \
  --user-confirmed
```

The command must be represented as an argv list, not a shell string. The wrapper defaults to plan-only unless both `--execute` and `--user-confirmed` are present.

## Run-Once Sequence

1. Calculate latest closed minute using the same N3 closed-minute policy.
2. No-op if no closed minute exists, current date mismatches `for_trade_date`, or the deterministic B2 run is already passed.
3. Generate child artifacts for the latest closed minute with write-artifacts behavior.
4. Verify generated JSON artifacts and B1/C1/B2 rollback SQL static safety.
5. Execute the supervisor bounded pass only when wrapper has `--execute --user-confirmed`.
6. Write a wrapper report for no-op, blocked, or supervisor result.

Child commands remain guarded and must still include `--execute --user-confirmed`.

## Idempotency

- Identical generated artifacts: `unchanged`, continue.
- Conflicting artifacts: `BLOCKED` before supervisor execution.
- Passed B2 watermark: no-op before artifact generation and child execution.
- Partial stage handling remains supervisor responsibility.
- No new state table.

## Stop Policy

- No long-running worker.
- Future cron/launchd may call the wrapper once per minute only after a separate final activation approval.
- Any generation, validation, or child failure stops the current pass and writes a report.
- Supervisor still stops after the first failed child stage.

## Required Implementation Scope

- `scripts/run_n3_intraday_b1_c1_b2_auto_poll_once.py`
- `tests/test_n3_intraday_auto_poll_activation.py`
- `docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_ACTIVATION_COMMAND_COMPOSITION.md`
- `docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_ACTIVATION_COMMAND_COMPOSITION.json`

## Safety Proof

```text
wrapper_implemented_now=false
supervisor_execute_invoked=false
b1_c1_b2_execute_invoked=false
database_written=false
cron_launchd_installed_or_enabled=false
outbox_inbox_checkpoint_consumed_or_updated=false
n4_n5_n6_entered=false
worker_started=false
old_system_touched=false
delivery_push_voice_mobile=false
proposal_order_trade=false
sim_position_pnl_real_trade=false
```

## Decision

- allow auto-poll activation final gate now: `False`
- allow wrapper implementation gate: `True`
- next gate: `N3_INTRADAY_B1_C1_B2_AUTO_POLL_ACTIVATION_WRAPPER_IMPLEMENTATION_GATE`
