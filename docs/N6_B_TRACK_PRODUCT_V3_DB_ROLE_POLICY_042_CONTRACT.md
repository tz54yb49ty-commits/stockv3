# N6 B-track Product V3 DB Role Policy 042

Status: implementation draft; feature flags remain disabled. Migration, role
creation, credential installation, executor startup, and 8786 release are
separate gates.

## Authority

The only Web authority input is the SHA-256 hash calculated by the server from
the opaque session cookie. `n6_btrack_resolve_authority` validates the active
`user_session`, active `user_account`, and exactly one persistent active
`n6_principal` owned by that user. It returns no row for zero or multiple
principals. Client principal fields and custom PostgreSQL GUCs are not inputs.
There is no session-scoped fallback principal.

Every 042 function is `SECURITY DEFINER`, uses a fixed `pg_catalog` search path,
fully qualifies N6 objects, avoids dynamic SQL, and has PUBLIC execute revoked.

## Repository boundary

- Authentication, login/logout, and A-track/admin continue through the existing
  authentication repository.
- B-track state-changing V3 routes require a separately injected
  `N6BTrackAuthorityRepository` and pass only the server-produced session hash.
- Enabling a feature flag without the separate repository remains fail-closed.
- The restricted repository can invoke only the explicit 042 function allowlist;
  it has no generic SQL/table API.

## Permission matrix

| Surface | `n6_btrack_web` | `n6_virtual_executor` |
|---|---|---|
| Session/principal | resolve current active authority | none |
| Monitor | scoped list/upsert/remove | none |
| Realtime scope | scoped list/upsert/remove | none |
| Proposal | scoped list/create; pending to confirmed/expired | claim/finish only |
| Virtual trade | scoped list | none |
| Projection/monitor tables | no direct privileges | no direct privileges |
| Order/trade/position/cash tables | no direct privileges | no direct privileges |

The executor functions only implement proposal state ownership. They do not
contain order filling, position mutation, cash accounting, quote fetching, or a
scheduler.

## Proposal state ownership

```text
Web:      create pending; pending -> confirmed | expired
Executor: confirmed -> processing; processing -> executed | failed
```

The transition trigger checks `SESSION_USER`. Web cannot set executor result
fields, and executor cannot create a proposal or modify monitor/realtime scope.
The object owner remains available only for separately governed maintenance.

## Migration and rollback

042 does not create or alter roles. It first requires both roles to exist with
`LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
NOBYPASSRLS`. Credentials, service files, and release environment are outside
Git and outside this migration.

Rollback revokes the exact grants and drops only 042 functions/trigger. It is
blocked while either role has another active connection or any proposal is
`processing`. Schema 041 and all business history are preserved.

## Frozen non-goals

- No role/password/credential provisioning.
- No DSN, credential material, session token, or CSRF value in SQL/docs/logs.
- No feature flag activation.
- No executor implementation or runtime installation.
- No N1-N5, outbox, projection poller, quote scheduler, schema 041, or 8786
  mutation.
