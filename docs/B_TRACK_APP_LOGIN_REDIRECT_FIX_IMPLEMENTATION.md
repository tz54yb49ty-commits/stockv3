# B Track App Login Redirect Fix Implementation

Gate: B_TRACK_APP_LOGIN_REDIRECT_FIX_IMPLEMENTATION_GATE

Result: IMPLEMENTATION_PASS

Layer role: N6_user

Date: 2026-06-07

## 1. Scope

This implementation fixes the B Track ordinary user entry flow:

```text
/n6/app -> /n6/login?next=/n6/app -> /n6/app
```

The change is limited to login redirect, session cookie response behavior, and
B Track app-shell unauthenticated entry handling.

No database business fact, N4/N5/N6 fact, outbox, worker, proposal, order,
trade, position, PnL, sim, voice, mobile, or real trade path is modified.

## 2. Modified Files

```text
src/ashare_v3/web/n6_user_app.py
src/ashare_v3/web/templates/n6_login.html
tests/test_n6_user_app.py
docs/B_TRACK_APP_LOGIN_REDIRECT_FIX_IMPLEMENTATION.md
docs/B_TRACK_APP_LOGIN_REDIRECT_FIX_IMPLEMENTATION.json
```

## 3. Redirect Contract

Implemented behavior:

```text
GET /n6/app unauthenticated
-> 302 /n6/login?next=/n6/app

GET /n6/app/account unauthenticated
-> 302 /n6/login?next=/n6/app/account

POST /api/n6/auth/login?next=/n6/app
-> 302 /n6/app

POST /api/n6/auth/login without next, admin user
-> 302 /n6/action-events

POST /api/n6/auth/login without next, ordinary user
-> 302 /n6/app

POST /api/n6/auth/login?next=http://evil.com, admin user
-> 302 /n6/action-events
```

Allowed `next` values are restricted to:

```text
/n6/app
/n6/app/...
```

Missing, absolute, cross-origin, or non-B-track next values are rejected and
fall back to the authenticated user's role default:

```text
admin -> /n6/action-events
ordinary user -> /n6/app
```

## 4. Login Proof

The login page stores a sanitized B Track next target only when one is present.
Direct `/n6/login` and malicious next values keep the hidden next empty, so
the server's authenticated role default controls the destination.

Successful login creates the normal N6 session and returns:

```text
302 Location: <safe B Track next or role default>
Set-Cookie: ashare_v3_n6_session=...
```

Direct admin login without a next target defaults to `/n6/action-events`.
Direct ordinary user login without a next target defaults to `/n6/app`.

## 5. A Track Compatibility Proof

A Track routes are not moved under the B Track next policy.

Confirmed compatibility:

```text
GET /n6/action-events after login -> 200
GET /api/n6/ui/v1/virtual-account after login -> 200
```

Existing A Track unauthenticated redirect behavior remains separate from the B
Track `/n6/app` entry redirect.

## 6. Forbidden Scope Proof

This gate does not introduce or modify:

```text
database business fact writes
N4 facts
N5 facts
N6 projection/card facts
outbox consume/update
worker startup
proposal generation
order generation
trade generation
position update
PnL generation
real trade submission
```

The B Track app and API route scan remains GET-only.

## 7. Verification

Fresh verification commands:

```text
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
PYTHONPATH=src python3 -m compileall src/ashare_v3/web/n6_user_app.py tests/test_n6_user_app.py
python3 route scan for /n6/app and /api/n6/app/v1
Codex Browser open http://127.0.0.1:8786/n6/app
```

Observed results:

```text
unittest: Ran 68 tests, OK
compileall: exit 0
route scan: GET_ONLY_PASS
browser B Track entry: final URL /n6/login?next=/n6/app, hidden next /n6/app
browser direct login: final URL /n6/login, hidden next empty
```

## 8. Next Gate

```text
B_TRACK_APP_LOGIN_REDIRECT_FIX_POST_REVIEW_GATE
```
