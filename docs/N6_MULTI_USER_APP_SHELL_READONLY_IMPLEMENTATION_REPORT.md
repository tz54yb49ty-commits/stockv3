# N6 Multi User App Shell Readonly Implementation Report

Status: IMPLEMENTATION_PASS

Gate: N6_MULTI_USER_APP_SHELL_READONLY_IMPLEMENTATION_GATE

Layer role: N6_user

## Scope

Implemented B-track read-only app shell and GET-only API under independent prefixes:

- Pages: `/n6/app/...`
- APIs: `/api/n6/app/v1/...`

This implementation does not modify A-track admin console routes or `/api/n6/ui/v1/...`.

## API Summary

- `GET /api/n6/app/v1/me`
- `GET /api/n6/app/v1/account`
- `GET /api/n6/app/v1/watchlist`
- `GET /api/n6/app/v1/signals`
- `GET /api/n6/app/v1/proposals`
- `GET /api/n6/app/v1/portfolio`
- `GET /api/n6/app/v1/pnl`
- `GET /api/n6/app/v1/ai-users`
- `GET /api/n6/app/v1/leaderboard`

All endpoints require an authenticated N6 session and current B-track principal scope.

## Page Summary

- `/n6/app`
- `/n6/app/dashboard`
- `/n6/app/account`
- `/n6/app/watchlist`
- `/n6/app/signals`
- `/n6/app/proposals`
- `/n6/app/portfolio`
- `/n6/app/pnl`
- `/n6/app/ai-users`
- `/n6/app/leaderboard`

The page shell is independent from A-track N6_UI_v1 admin console navigation.

## Principal Scope

The current principal resolver maps the authenticated admin user to exactly one active B-track principal. If no scoped principal exists, or if principal resolution is ambiguous, B-track APIs return `403 principal_scope_unavailable` and do not fall back to unscoped data.

## Read-Only Boundary

Allowed sources for signal display:

- reviewed N5/N6 artifacts
- N6 shadow projection
- N6 signal card
- N6 dashboard artifact
- approved/reviewed N3 snapshot
- reviewed valuation policy

Forbidden sources:

- raw K
- N1 raw facts
- direct live market
- N4 raw facts bypass
- N5 raw facts bypass

## Forbidden Scope

No implementation path creates proposal/order/trade rows, updates position/PnL, materializes leaderboard, consumes outbox, starts workers, or triggers delivery/push/voice/mobile/sim/real trade.

## Validation

- Targeted unittest: `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'`
- Compileall, JSON parse, and `git diff --check` are required before post-review registration.

