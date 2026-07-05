# B Track App Principal Scope Fix Implementation

Gate: B_TRACK_APP_PRINCIPAL_SCOPE_FIX_IMPLEMENTATION

Result: IMPLEMENTATION_PASS

Layer role: N6_user

Date: 2026-06-07

## Scope

Fix `/n6/app` showing raw `principal_scope_unavailable` for active ordinary
users that do not yet have an `n6_principal` row.

The resolver now keeps formal `n6_principal` rows as the first choice. If no
row exists and the authenticated session role is `user`, it derives a
principal-scoped readonly identity from the session:

```text
principal_id = session.user_id
principal_type = human_user
owner_user_id = session.user_id
principal_status = active
```

Admin users are not silently downgraded or broadened. If an admin has no formal
principal row, B Track remains blocked.

## Boundary

This change does not write database business facts, create principals, update
N4/N5/N6 facts, consume outbox, start workers, or create proposal/order/trade,
position, PnL, sim, voice, mobile, or real trade state.

All B Track page/API routes remain GET-only and subsequent data reads remain
scoped by `principal_id` and `principal_type`.

## Verification

```text
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
PYTHONPATH=src python3 -m compileall src/ashare_v3/web/n6_user_app.py tests/test_n6_user_app.py
python3 route/source scan
```

Observed:

```text
unittest: Ran 68 tests, OK
compileall: exit 0
route scan: GET_ONLY_PASS
principal scan: SESSION_SCOPED_HUMAN_PRINCIPAL_PASS
```
