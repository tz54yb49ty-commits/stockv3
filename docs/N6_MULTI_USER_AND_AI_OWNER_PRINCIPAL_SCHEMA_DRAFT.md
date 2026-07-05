# N6 Multi User and AI Owner Principal Schema Draft

Status: SCHEMA_DRAFT_PASS

Layer role: N6_user

Date: 2026-06-04

This gate freezes a Track B owner / principal / account schema draft only. It
does not create a SQL migration, execute DDL, write database rows, modify
N6_UI_v1, modify existing APIs, modify existing projection rows, modify the
shadow pipeline, consume outbox rows, start workers, deliver notifications,
push to voice/mobile, run sim, create positions, or place real trades.

## 1. Inputs

Required source artifacts:

```text
docs/N6_MULTI_USER_AND_AI_SPEC_v1.md
docs/N6_MULTI_USER_AND_AI_SPEC_v1_TRACEABILITY.md
docs/N6_MULTI_USER_AND_AI_ARCHITECTURE_v1.md
docs/N6_MULTI_USER_AND_AI_ARCHITECTURE_TRACEABILITY_v1.md
```

Schema references read for field alignment:

```text
sql/014_condition_display_basis_schema.sql
sql/020_n6_user_projection_schema.sql
sql/001_raw_ingestion_schema.sql
```

The source spec remains a design artifact. This schema draft does not upgrade
DESIGN_ONLY source rules into IMPLEMENTATION_PASS.

## 2. Draft Goal

Track B needs one canonical owner model that can represent:

```text
human user
admin user
AI user
system-owned defaults
virtual account ownership
strategy ownership
watchlist ownership
principal-scoped signal visibility
future leaderboard approved-source reads
```

The draft keeps current Track A tables intact and treats future Track B tables
or views as a separate gated extension.

## 3. Principal Model

Suggested logical object: `n6_principal`.

| Field | Draft type | Required | Notes |
|---|---|---|---|
| `principal_id` | text or bigint identity | yes | Canonical owner root for Track B rows. |
| `principal_type` | enum | yes | `human_user`, `ai_user`, `admin`, `system`. |
| `owner_user_id` | bigint nullable | conditional | References current `user_account.user_id` for `human_user` and `admin`. |
| `owner_ai_user_id` | bigint nullable | conditional | References future AI user identity for `ai_user`; may be deferrable in a future migration. |
| `principal_status` | enum | yes | Suggested values: `active`, `disabled`, `deleted`, `system_reserved`. |
| `created_at` | timestamptz | yes | Creation audit. |
| `updated_at` | timestamptz | yes | Update audit. |

Principal invariants:

```text
principal_id is the owner key for Track B.
principal_type=human_user requires owner_user_id and no owner_ai_user_id.
principal_type=admin requires owner_user_id and no owner_ai_user_id.
principal_type=ai_user requires owner_ai_user_id and no owner_user_id.
principal_type=system requires neither owner_user_id nor owner_ai_user_id.
deleted principals remain audit-visible and are not physically reused.
principal rows do not grant permission by themselves; permission is evaluated
through role, visibility, and policy gates.
```

Future migration note:

```text
The AI principal relation may be implemented with deferrable references, a
principal_id column on n6_ai_user, or a separate binding table. This draft
freezes the ownership semantics, not the physical SQL shape.
```

## 4. Human User Model

Current source object: `user_account`.

Suggested Track B read model: `v_n6_human_user`.

| Field | Source / draft mapping | Notes |
|---|---|---|
| `user_id` | `user_account.user_id` | Current human user identity. |
| `login_identity` | `user_account.login_name` | Login name; password hash is never exposed. |
| `display_name` | `user_account.display_name` | Display-only label. |
| `role` | `user_account.role` | Current values: `admin`, `user`; admin also maps to principal_type `admin`. |
| `status` | `user_account.status` | Current values: `active`, `disabled`, `deleted`. |

Human user rules:

```text
password_hash and password_hash_algo remain authentication-only fields.
Track B user display views must not expose password_hash, session token hashes,
or client_info_json.
Admin and regular user have the same monitor, portfolio, and notification
preview feature scope unless an admin-only governance page is being rendered.
```

## 5. AI User Model

Suggested logical object: `n6_ai_user`.

| Field | Draft type | Required | Notes |
|---|---|---|---|
| `ai_user_id` | text or bigint identity | yes | AI identity. |
| `principal_id` | references `n6_principal` | yes | Owner principal for AI rows. |
| `ai_name` | text | yes | Display name. |
| `strategy_profile_id` | nullable reference | no | Default strategy profile, future-gated. |
| `status` | enum | yes | Suggested values: `active`, `disabled`, `deleted`, `sandbox_only`. |
| `readable_scope_policy` | jsonb or policy ref | yes | AI allowed-source policy. |

AI readable scope policy must allow only:

```text
approved N2 summaries
approved N3 projection summaries
reviewed N4 trigger artifacts
reviewed N5 action artifacts
N6 shadow projection
N6 reviewed artifacts
```

AI readable scope policy must deny:

```text
raw K
live market data direct connection
N1 raw facts outside approved membership facts
condition_basis
condition_pool
minute_target_scope
N3 raw facts
N4 raw facts
N5 raw facts
real account
real funds
real position
broker session
real trade API
```

## 6. Account Model

Suggested logical object: `n6_principal_account`.

| Field | Draft type | Required | Notes |
|---|---|---|---|
| `account_id` | text or bigint identity | yes | Canonical account identity. |
| `principal_id` | references `n6_principal` | yes | Account owner. |
| `account_type` | enum | yes | `virtual`, `ai_virtual`, `admin_shadow`. |
| `virtual_account_id` | nullable reference | conditional | References future virtual account or current shadow `user_sim_account_id` through an adapter. |
| `account_status` | enum | yes | Suggested values: `active`, `disabled`, `deleted`, `closed`. |

Account rules:

```text
account_type=virtual belongs to a human_user or admin principal.
account_type=ai_virtual belongs to an ai_user principal.
account_type=admin_shadow belongs to an admin principal and is for governance
preview only.
No Track B account is a real broker account.
No account row may carry broker credentials or real funds.
Current user_sim_account remains shadow simulation evidence only; future
canonical virtual account schema needs a separate gate.
```

## 7. Watchlist Ownership

Current source object: `user_watchlist`.

Suggested Track B ownership extension: principal-scoped watchlist ownership.

| Field | Draft type | Required | Notes |
|---|---|---|---|
| `watchlist_id` | bigint or adapter key | yes | Current `user_watchlist.user_watchlist_id` or future Track B id. |
| `principal_id` | references `n6_principal` | yes | Owner principal. |
| `visibility` | enum | yes | `private`, `shared`, `admin`, `public_leaderboard`. |

Visibility rules:

```text
private is default.
shared requires an explicit future grant table or artifact.
admin visibility is governance-only and must not expose secrets.
public_leaderboard is aggregate-only and must not expose holdings, funds,
sessions, prompts, raw traces, or private watchlist items.
Watchlists do not expand N2/N3/N4/N5 scope and do not update upstream facts.
```

## 8. Strategy Ownership

Suggested logical object: `n6_strategy`.

| Field | Draft type | Required | Notes |
|---|---|---|---|
| `strategy_id` | text or bigint identity | yes | Immutable strategy identity or family id. |
| `principal_id` | references `n6_principal` | yes | Owner principal. |
| `strategy_type` | enum/text | yes | Examples: `manual_filter`, `ai_generated`, `marketplace`, `system_default`. |
| `policy_version` | text | yes | Version of strategy policy. |
| `policy_hash` | text | yes | Hash of immutable policy content. |
| `status` | enum | yes | Suggested values: `draft`, `reviewed`, `active`, `disabled`, `archived`, `deleted`. |

Strategy rules:

```text
strategy belongs to exactly one owner principal.
strategy versions are immutable after activation.
policy_hash is required before execute/materialization gates.
strategy output cannot update N2/N3/N4/N5 facts or consume outbox rows.
AI-generated strategies must carry risk labels before marketplace publication.
```

## 9. Display Input Boundary

N6 user, principal, and AI display flows may read only read-safe wrappers over:

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
index_membership_fact
board_membership_fact
user_projection_run
user_signal_projection
user_signal_card
user_notification_queue
reviewed artifacts
```

N6 display and Track B schema must not directly read:

```text
condition_basis
condition_pool
minute_target_scope
N3 raw facts
N4 raw facts
N5 raw facts
raw K
live market data direct connection
broker session
real account
real funds
real position
real trade API
```

Display enrichment rule:

```text
User-facing fields such as change percentage, target price, expected return,
industry name/code, and index name/code should be copied into N6 projection
rows at projection time when they are part of a reviewed N6 projection run.
For later read-only UI enrichment, N6 should use only the proposed read-only
views over N2 display_basis and N1 membership_fact. N6 must not recompute N2,
scan N4/N5 raw facts, or pull live行情 directly.
```

Board type enum:

```text
tdx_industry
tdx_concept
tdx_region
tdx_other
```

## 10. Suggested Read-Only Views

These are proposals only. No view is created in this gate.

| View | Source table | Purpose | Required guard |
|---|---|---|---|
| `v_n6_stock_condition_display_basis` | `stock_condition_display_basis` | Stock display fields for N6 UI, strategies, and AI summaries. | Read-only; expose display-safe columns and source lineage; no raw upstream re-interpretation. |
| `v_n6_index_condition_display_basis` | `index_condition_display_basis` | Index display fields and top-index strategy context. | Read-only; no direct index condition_basis scan. |
| `v_n6_board_condition_display_basis` | `board_condition_display_basis` | Board display fields, strong-board filters, and board type. | Read-only; board_type limited to the canonical enum. |
| `v_n6_index_membership_fact` | `index_membership_fact` | Stock-to-index membership for display joins. | Read-only; expose identity keys, codes, names, trade_date/source_version. |
| `v_n6_board_membership_fact` | `board_membership_fact` | Stock-to-board membership for display joins. | Read-only; expose identity keys, codes, names, board_type, trade_date/source_version. |

Suggested view column families:

```text
identity: asset_kind, identity_key, code, name, display_code, display_name
date/source: trade_date, for_trade_date, source_trade_date, run_id, source_version
display: display_title, display_summary, recommendation_level, selected_signal_types
price/context: buy_target_price, sell_target_price, target_price_summary_json
period: period_grade_y/q/m/w/d, period_transition_y/q/m/w/d
membership: stock_identity_key, index_identity_key, board_identity_key, board_type
quality: display_status, quality_status, missing_fields_json
lineage: source artifact ids or display run ids that are already approved for N6
```

View constraints for a future migration gate:

```text
views must be read-only
views must not include password/session/broker/real-account fields
views must not expose raw_payload by default
views must not create cross-layer write paths
views must be reviewed before any AI readable_scope_policy references them
```

## 11. Track A / Track B Isolation

This draft is Track B only.

Still forbidden:

```text
modifying N6_UI_v1
modifying existing APIs
modifying existing N6 projection/card/queue schema
modifying shadow projection runners
changing N5 outbox consumption behavior
starting delivery/push/voice/mobile/sim/position/real trade
```

Any future adapter from this principal model to Track A UI must have a separate
compatibility gate.

## 12. Rollback / Replay Contract

Because this gate creates no SQL migration and writes no database rows, there is
no database rollback to execute.

Future Track B migrations must provide rollback guards:

```text
schema rollback hard-fails if Track B business rows exist
business rollback is scoped by run_id or principal/account/strategy run id
rollback hard-fails if linked decision/sim/voice/mobile/position/real-trade refs exist
rollback never touches N5 outbox or N1-N5 facts
```

Future projection replay remains N6-scoped:

```text
replay may rebuild N6 principal-scoped projections from approved N5 events and
approved N2/N1 display views
replay must not consume or update N5 outbox unless a separate outbox-consumption
gate explicitly authorizes it
```

## 13. Remaining Gaps

```text
no SQL migration for n6_principal / n6_ai_user / n6_principal_account
no principal binding for existing user_account rows
no AI readable_scope_policy enforcement implementation
no principal-scoped watchlist migration
no strategy ownership schema migration
no read-only view migration
no permission grant model for shared visibility
no virtual account canonical schema beyond existing shadow user_sim_* tables
no AI decision/evaluation/leaderboard/marketplace implementation
no adapter to N6_UI_v1
real trade remains disabled and out of scope
```

## 14. Next Allowed Gate

Allowed next step:

```text
runtime_control N6 multi-user and AI owner/principal schema draft review gate
```

Still blocked until separate gates:

```text
SQL migration
database write
DDL execute
business implementation
N6_UI_v1 modification
existing API modification
existing projection/shadow pipeline modification
outbox consumption/update
worker startup
delivery / push / voice / mobile / sim / position / real trade
```
