# N6 B-track Product V3 virtual stop-loss 049 contract

Status: implementation draft / exact-nine-file review gate. Migration, DB
connection, runtime, 8786, scheduler, feature activation, stage, and commit are
not authorized.

## Authority and inputs

This is an N6-only executor workflow. It reads only
`n6_virtual_quote_snapshot`, N6 virtual account/position/lot/proposal facts,
`n6_principal` for the proposal owner, and the canonical
`common_trade_calendar`. It never imports or calls an N3 freeze module or
N3N6Q adapter and never reads N1-N5 facts, outbox, or membership tables.

The three functions are `SECURITY DEFINER`, use `search_path=pg_catalog`, revoke
PUBLIC and `n6_btrack_web`, grant only `n6_virtual_executor`, and require zero
direct relation/sequence privilege for that role.

## Freeze

`n6_executor_freeze_next_stop_loss(text)` locks at most one principal-scoped
open stock position with `FOR UPDATE SKIP LOCKED`. The candidate must be in a
positive holding episode with `stop_loss_status=provisional_first_day` and a
known first-open date. The missing-quote path is retryable: it returns
`not_ready`, preserves `provisional_first_day`, and writes nothing.

After the first-day 15:05 final boundary, the function selects the last passed
SH/SZ snapshot whose provider `quote_minute` is 14:55-15:05 on that first day.
`fetched_at` is local completion lineage: it may be after 15:05 but may not
precede the provider minute or be in the future. A finite positive cumulative
`day_low` is frozen with its source snapshot, timestamp, policy, and next open
trade date. Same-episode adds preserve the freeze; only a reopened episode is
provisional again under the unchanged 046 buy semantics.

## Evaluate and rearm

`n6_executor_evaluate_next_stop_loss(text)` runs only in the current canonical
open trade date/session, locks at most one eligible position, and derives T+1
sellability exclusively from exact principal/account/position/identity/episode
lots with positive remaining quantity, matured `available_trade_date`, and
status `locked_t1|available`.

The newest N6 quote and the exactly preceding minute must both be passed SH/SZ,
finite positive, not future, and fresh by both `quote_minute` and `fetched_at`
within 120 seconds. Both prices must be at or below the frozen stop. Gaps,
spikes, rebounds, stale/bad/BJ/wrong-scope rows create no proposal.

The proposal is immediately `confirmed`, expires in 60 seconds, and records
`confirmed_at`, deterministic `confirm_idempotency_key`, source
`position:episode:confirm_snapshot`, first/confirm snapshots, stop/trigger
prices, policy, and lineage. Pending/confirmed/processing or executed proposals
permanently block the same episode. After expired/rejected/failed, two adjacent
passed minutes strictly above the stop must occur after that proposal and before
a later new two-minute breach; the new confirm snapshot makes a new source key.

## Apply

049 replaces the existing 046
`n6_executor_apply_claimed_proposal(bigint,text)` definition without changing
signal/manual-position behavior. Stop-loss apply rechecks exact source position
and episode, open/frozen/effective state, exact matured lots, and the latest N6
SH/SZ quote. Both quote clocks must be nonfuture and at most 120 seconds old;
price must remain at or below the stop. The server quote and all matured lots
determine fill price and quantity. Existing 046 atomic order/trade/cash/lot/
position/event/proposal writes and `fill_quote_snapshot_id` remain authoritative.

Transient quote absence/quality/freshness returns `ok=false`, so the 048 outer
transaction rolls back the claim for retry. Quote recovery, position/episode
drift, or no matured T+1 lot updates only the proposal to a terminal status with
a reason and returns `ok=true`; account/order/trade/cash/lot/position writes are
zero.

## Rollback

Rollback drops only the two 049 freeze/evaluate functions and restores the
exact 046 apply definition and ACL. It never deletes quote, proposal, order,
trade, position, cash, lot, or 041-048 history.
