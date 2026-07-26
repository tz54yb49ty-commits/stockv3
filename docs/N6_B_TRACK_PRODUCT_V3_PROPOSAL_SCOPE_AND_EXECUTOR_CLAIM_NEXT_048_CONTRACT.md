# N6 B-track proposal scope and executor claim-next 048 contract

Status: implementation draft; exact-eight-file review gate only.

## Boundary

This is an `N6_user`, FULL MODE, function-only migration. It creates no table,
index, role or trigger and grants no direct relation or sequence privilege.
This gate does not connect to PostgreSQL, execute migration or rollback, start
8786/runtime/scheduler, enable flags, stage or commit.

## Proposal authority

`n6_btrack_proposal_create(text,text,bigint)` requires exactly one active
principal-owned virtual account and exactly today's Asia/Shanghai open row from
`common_trade_calendar`. A signal projection must freeze the same
`for_trade_date`; historical, future, missing and closed-calendar requests
produce zero DML.

Signal content is read only from
`user_projection_run -> user_signal_projection -> user_signal_card`.
Reference/action price, target price and score are pass-through frozen values;
N6 does not read common_event_outbox, N2-N5 raw tables, membership, or perform
message enrichment.

Stock buy authority is any active stock monitor or realtime stock scope that
matches the current unique approved
`v_n6_stock_condition_display_basis (source_trade_date, for_trade_date, run_id,
identity_key)` batch, or the principal/account's current positive-quantity open
stock position. A monitor must also carry the exact 045 frozen lineage. Stock
sell authority is only that current open position when at least one exactly
scoped `n6_virtual_position_lot` has `remaining_quantity > 0`,
`available_trade_date <= current_trade_date`, and `lot_status` in
`locked_t1/available`.

Realtime scope is a long-lived whitelist: its 044 snapshot freezes only the
identity and join-time trade date. Authority requires an active, non-deleted
`single_row` for the exact principal/user/stock identity and a self-consistent
snapshot identity. The outer approved-identity join must independently prove
that identity remains in today's current approved stock view and that the
projection is for today. The historical realtime snapshot date is not compared
to today's date or source run. A yesterday-added row therefore remains valid
only while the identity is still approved today.
Signal sell freezes its `virtual_position_id` in `source_lineage_json` and its
positive `holding_episode_no` in the proposal column. Manual position remains a
same-principal/account open stock position with an exactly matching matured
positive-remaining lot.
Identity, principal, user, account, direction, action state, reference price,
target price, date and episode all fail closed.

`n6_virtual_position.available_quantity` is not proposal-time cross-day
authority because it is refreshed only by a fill transaction. Proposal-create
performs no lot or position update. Schema 046 remains final execution
authority: it locks lots, promotes T+1-available quantity, reconciles the
position, and applies the fill in one transaction.

Canonical stock identity comes only from the N6 projection/position rows. The
function does not join `stock_identity`. Signal trade date, score, action state
and display prices use only frozen `display_payload_json` and
`card_payload_json`; `source_payload_json` is never selected or used as a
fallback.

## Claim-next

`n6_executor_claim_next_proposal(text)` is `SECURITY DEFINER` with
`search_path=pg_catalog`. PUBLIC and `n6_btrack_web` have no execute authority;
only `n6_virtual_executor` may execute it and that role retains zero direct
table/sequence privileges.

`CREATE OR REPLACE` preserves the existing proposal-create owner and ACL. The
migration does not alter function ownership; its post-check requires owner
`ashare_v3_user`, `SECURITY DEFINER`, fixed search path, PUBLIC revoke, Web-only
proposal-create execution, and Executor-only claim execution.

One statement selects at most one unexpired `confirmed` proposal ordered by
`confirmed_at, created_at, proposal_id`, locks it with
`FOR UPDATE SKIP LOCKED`, and atomically changes it to `processing` with the
executor run id. No candidate returns `no_claimable_proposal`; expired
confirmed rows are not claimed or bulk-updated.

## Runner and rollback

Without `--execute`, the one-shot performs zero DB connections, claims and DML.
Execute defaults to claim-next; optional `--proposal-id` is a controlled canary.
Claim and 046 apply share one outer transaction. No candidate rolls back and
returns; apply rejection or exception rolls back the claim, so this invocation
leaves no processing residue. The runner accepts no DSN/password argv or env,
requires exact `PGSERVICE=n6_virtual_executor`, processes at most one proposal,
and adds no loop, thread, plist or scheduler.

Rollback drops only the 048 claim-next function/grant, restores the Schema 042
proposal-create text and original claim ACL, and preserves Schemas 041-047 and
all proposal/trade/position history.
