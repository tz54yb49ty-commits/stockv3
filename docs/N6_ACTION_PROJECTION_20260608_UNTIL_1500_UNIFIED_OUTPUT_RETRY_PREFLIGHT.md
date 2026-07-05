# N6 Action Projection 20260608 Until 15:00 Unified Output Retry Preflight

- result: `PREFLIGHT_PASS`
- P0/P1/P2: `0/5/2`
- notification_queue_policy: `deferred`
- execute performed: `false`
- database write performed: `false`

## Checks

- N5 action run exists and status is passed.
- N5 outbox pending distribution is ActionExecuted=`7`, ActionBlocked=`549`.
- delivered/delivering=`0/0`.
- target N6 scoped baseline rows are all `0`.
- downstream refs are `0`.
- metric trace is present for `556/556` action facts.
- effective planned writes are run/projection/card/queue = `1/556/556/0`.

## Non-Blocking Display Warnings

- display_basis_missing=`556`
- current_price_missing=`556`
- target_price_missing=`556`
- expected_return_pct_missing=`556`
- board_context_missing=`556`

These are display-only warnings and must not trigger cross-layer backfill from N4/N3/N2 naked facts.
