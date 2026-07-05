# N6 Phase 2 Owner Principal Initialization Execute Contract

Status: CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-05

This contract freezes the executable boundary for the Track B Phase 2
owner/principal initialization. It does not execute the runner, write database
rows, consume or update outbox rows, start workers, modify N6_UI_v1, modify
existing APIs, modify projection/shadow pipeline rows, deliver notifications,
push to voice/mobile, run sim, create positions, or place real trades.

## 1. Basis

Source artifacts:

```text
docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_DRAFT.md
docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_DRAFT.json
docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_PREFLIGHT_DRAFT.md
docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_PREFLIGHT_DRAFT.json
sql/N6_phase2_owner_principal_seed_rollback_draft.sql
runtime_control APPROVED_WITH_CHANGES review
```

Schema references:

```text
sql/036_n6_multi_user_ai_owner_principal_schema.sql
sql/037_n6_view_readonly_permission.sql
```

## 2. Seed Run

```text
seed_run_id = n6_phase2_owner_principal_initialization_20260605_v1
policy_version = n6_phase2_owner_principal_seed_policy_v1
policy_hash = 8334cb658002542819d0c970138b0bb3b8f5d8dadb414777408fcbd6aac6a8c4
created_by_gate = N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_EXECUTE_CONTRACT_GATE
rollback_sql = sql/N6_phase2_owner_principal_seed_rollback.sql
```

## 3. Planned Writes

The execute path may write only:

| Table | Planned rows |
|---|---:|
| `n6_principal` | 2 |
| `n6_principal_account` | 0 |
| `n6_ai_user` | 0 |
| `n6_watchlist_ownership` | 0 |
| `n6_strategy` | 0 |

No other table is in scope.

## 4. Seed Rows

### 4.1 Admin Principal

Target:

```text
n6_principal
```

Fields:

| Field | Value |
|---|---|
| `principal_id` | DB-generated identity, reported after execute |
| `principal_type` | `admin` |
| `owner_user_id` | Existing active `user_account.user_id` where `login_name='admin'` |
| `principal_status` | `active` |
| `principal_label` | `Initial Admin Principal` |
| `principal_policy_json.seed_run_id` | `n6_phase2_owner_principal_initialization_20260605_v1` |
| `principal_policy_json.seed_key` | `phase2_admin_principal__user_account_admin` |
| `principal_policy_json.policy_version` | `n6_phase2_owner_principal_seed_policy_v1` |
| `principal_policy_json.policy_hash` | `8334cb658002542819d0c970138b0bb3b8f5d8dadb414777408fcbd6aac6a8c4` |
| `principal_policy_json.source_artifact` | `docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_EXECUTE_CONTRACT.md` |
| `principal_policy_json.created_by_gate` | `N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_EXECUTE_CONTRACT_GATE` |

Rationale:

```text
036 CHECK permits principal_type='admin' only when owner_user_id is not null.
The existing admin user is the owner root for governance principal scope.
```

### 4.2 System Principal

Target:

```text
n6_principal
```

Fields:

| Field | Value |
|---|---|
| `principal_id` | DB-generated identity, reported after execute |
| `principal_type` | `system` |
| `owner_user_id` | `NULL` |
| `owner_ai_user_id` | not present in 036 schema; logically `NULL` |
| `principal_status` | `system_reserved` |
| `principal_label` | `N6 System Principal` |
| `principal_policy_json.seed_run_id` | `n6_phase2_owner_principal_initialization_20260605_v1` |
| `principal_policy_json.seed_key` | `phase2_system_principal__n6_system` |
| `principal_policy_json.policy_version` | `n6_phase2_owner_principal_seed_policy_v1` |
| `principal_policy_json.policy_hash` | `8334cb658002542819d0c970138b0bb3b8f5d8dadb414777408fcbd6aac6a8c4` |
| `principal_policy_json.source_artifact` | `docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_EXECUTE_CONTRACT.md` |
| `principal_policy_json.created_by_gate` | `N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_EXECUTE_CONTRACT_GATE` |

Rationale:

```text
system principal is only a future system-default owner root.
It is not a login user, account, strategy runner, AI actor, or trade actor.
```

## 5. Explicitly Forbidden

The execute path must not create or modify:

```text
admin_shadow account
reserved AI principal
n6_ai_user
virtual account
virtual order
virtual position
watchlist
strategy
AI decision
AI evaluation
virtual_intent
user_account
user_session
user_projection_run
user_signal_projection
user_signal_card
user_notification_queue
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
N1-N5 facts
delivery / push / voice / mobile / sim / position / real trade
```

## 6. Runner Contract

Executable command for a future user-confirmed gate:

```bash
PYTHONPATH=src:scripts python3 scripts/run_n6_owner_principal_initialization_once.py \
  --seed-run-id n6_phase2_owner_principal_initialization_20260605_v1 \
  --contract-path docs/N6_PHASE2_OWNER_PRINCIPAL_INITIALIZATION_execute_contract.json \
  --execute \
  --user-confirmed
```

Runner requirements:

```text
missing --execute => BLOCKED before write
missing --user-confirmed => BLOCKED before write
contract status must be CONTRACT_PASS
contract seed_run_id must match CLI seed_run_id
contract planned rows must be exactly 2/0/0/0/0
preflight must PASS before write
single transaction writes exactly two n6_principal rows
post report must not include password_hash or session_token_hash
```

## 7. Rollback Contract

Rollback path:

```text
sql/N6_phase2_owner_principal_seed_rollback.sql
```

Rollback must:

```text
require n6.seed_run_id = n6_phase2_owner_principal_initialization_20260605_v1
hard-fail before first DELETE
delete only n6_principal rows whose principal_policy_json.seed_run_id matches
hard-fail if linked account/watchlist/strategy/ai/virtual refs exist
not drop 036 tables/views
not revoke/drop 037 permissions
not touch N1-N6 facts/outbox
```

## 8. Execute Gate Status

This contract is ready for runtime_control execute final gate review. It does
not itself authorize execution; execution still requires explicit user
confirmation with the command above.
