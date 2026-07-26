# N6 Strategy Center Temporal Confluence V2 — Shadow Canonical

\`\`\`text
document_status=APPROVED_FOR_SHADOW_ONLY
strategy_version=N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2
proposed_policy=n6_strategy_center_matcher_v2
approval_status=ONE_TIME_SHADOW_FAST_LANE_APPROVAL_ACCEPTED
canonical_research_room_thread_id=019f7ab7-7385-70a0-93d9-5e3e585e85b1
source_package_id=N6_SC_TEMPORAL_CONFLUENCE_V2_CANDIDATE_20260723
source_candidate_sha256=94f5a6d88717688bfe079930edb956c20acd6c0c66aef870b332d5c2b221e489
implementation_authority=SHADOW_ONLY
autonomous_trading_authorized=false
real_trading_authorized=false
proposal_authorized=false
order_authorized=false
trade_authorized=false
position_lot_cash_mutation_authorized=false
\`\`\`

## 1. Authority and scope

This document promotes the exact approved candidate above into the canonical
Shadow strategy contract. Any change to the package id, strategy version, source
candidate bytes, or rule semantics invalidates the one-time approval and must
fail closed.

The strategy is display-only and Shadow-only. It may write only the existing N6
Strategy Center selection, match projection, and match-change resources under
their separately approved runtime contract. It never authorizes a proposal,
order, trade, position, lot, cash mutation, autonomous trading, real trading,
voice, mobile delivery, or an N1–N5 write.

## 2. Signal coherence

- Stock, member-board, and member-index evidence must have the same canonical
  direction, either \`buy\` or \`sell\`. Missing or conflicting direction lineage
  fails closed.
- V2 reads the N5 standard event envelope time and payload direction as the
  source authority. The N6 projection copy and canonical signal DTO must agree
  with those source fields exactly; a missing, non-N5, or conflicting copy
  fails closed. Projection creation/update timestamps are never signal time.
- Evidence must be from one trade date. Cross-trade-date inheritance is
  forbidden.
- Time distance uses exact A-share trading seconds in \`Asia/Shanghai\`, with
  valid sessions \`09:30:00–11:30:00\` and \`13:00:00–15:00:00\`. The midday break
  does not increase a cross-session span, but an event timestamp inside the
  break is itself invalid and fails closed.
- At the first historical instant where a package can be confirmed, the matcher
  considers only evidence already available at that instant, chooses the
  smallest same-direction span, and applies stable identity/event-id tie breaks.
  Confirmation time is the latest required event time. Future events cannot be
  used to improve or rewrite that frozen evidence.
- The first persisted match/observation is the authority for its frozen event
  lineage, heat evidence, confirmation, and coherence key on later evaluator
  invocations. A late event with an earlier business timestamp cannot rewrite
  it. Only a newly discovered qualification-parent event may form a later
  coherence episode; a stock \`eligible→executed\` update or a heat-only event
  cannot independently create one.
- Historical reconstruction advances through the monotonic N6 projection
  arrival watermark one parent step at a time. Packages that first become
  confirmable at the same total arrival watermark are merged; distinct parent
  arrival watermarks remain distinct episodes. Batch replay and incremental
  tick replay must therefore produce byte-equivalent episode keys and hashes.
- Coherence levels are:

| Trading-minute span | Level | Qualification |
|---:|---|---|
| 0–15 | \`STRONG\` | qualified |
| 16–30 | \`MEDIUM\` | qualified |
| 31–60 | \`WEAK\` | display-only observation |
| greater than 60 | \`EXPIRED\` | no match |

A qualified result becomes stale 30 trading minutes after confirmation. \`WEAK\`
and stale results move to the observation surface and remain there through that
trade date's close. \`EXPIRED\` is never projected. The projection preserves its
frozen confirmation, stale-at evidence, and \`coherence_episode_key\`; later
parent evidence may create a new coherence episode but cannot overwrite an old
one. Within one N5 action episode, \`eligible\` to \`executed\` updates the same
coherence row and its state timeline without reselecting parent evidence.

## 3. Package rules

\`package_1:v2\` requires:

1. a stock signal;
2. a signal from one current member board;
3. a signal from at least one current member index;
4. one direction and a maximum qualified span of 30 trading minutes.

\`package_2:v2\` requires:

1. a stock signal;
2. a signal from one current member board;
3. one direction and a maximum qualified span of 30 trading minutes.

The seven membership indices are:

\`\`\`text
index:SH:000016
index:SH:000300
index:SH:000688
index:SH:000852
index:SH:000905
index:SZ:399006
index:SZ:399303
\`\`\`

Membership must use the authoritative as-of snapshot for the stock episode.
Missing, ambiguous, degraded, or mismatched as-of lineage fails closed.

## 4. Market heat

\`index:SH:000001\` and \`index:SZ:399001\` are market-heat inputs only. They do not
require stock membership and cannot create or qualify a candidate.

For each heat index, use its latest event in the preceding 30 trading minutes,
never later than the candidate confirmation time:

- both indices in the candidate direction:
  \`MARKET_HEAT_SUPPORTIVE\`;
- both indices opposite the candidate direction:
  \`MARKET_HEAT_ADVERSE\`;
- only one fresh signal or conflicting index directions:
  \`MARKET_HEAT_MIXED\`;
- neither has a fresh signal:
  \`MARKET_HEAT_NEUTRAL\`.

The heat state affects only the display label and deterministic candidate
ranking. It does not change package eligibility. Ranking is fixed as
\`SUPPORTIVE > NEUTRAL > MIXED > ADVERSE\`.

## 5. Projection and transport contract

- \`signal\` is the canonical \`/api/n6/app/v1/signals\` stock DTO,
  byte-equivalent after canonical JSON serialization. Strategy fields must never
  be injected into it.
- Strategy-only fields are returned under top-level \`confluence\`, including
  direction, coherence level/span, confirmation/stale times, freshness and
  qualification, per-package evidence, heat evidence, strategy version, and
  policy hash.
- \`matches[]\` contains only fresh \`STRONG\`/\`MEDIUM\` rows.
- \`observations[]\` contains \`weak_span\` and
  \`stale_after_confirmation\` rows.
- Match and observation changes share one monotonic change id and explicitly
  carry \`surface_kind=qualified_match|observation\`. SSE supports
  \`upsert/remove/reset\`; the 45-second full GET remains the correction path.
- A coherence episode exists on exactly one surface. If packages confirmed at
  the same instant have mixed levels, the row is qualified when at least one
  package is STRONG/MEDIUM; \`matched_packages\` contains only qualified
  packages while \`package_evidence[]\` retains the WEAK package evidence. Only
  an all-WEAK episode is a \`weak_span\` observation. Match and observation
  watermarks and quality summaries are returned separately, and ordering uses
  heat rank followed by confirmation time and stable identity keys.
- History is append-only across version migration. V1 users remain
  grandfathered until an individual V2 pending revision is replayed and
  atomically activated; global V1 retirement is a later, separate gate.
- The V2 Web/API is fail-closed for an active V1 selection. It returns
  \`migration_required=true\`, reports the number of hidden legacy rows in
  \`legacy_v1_suppressed_count\`, and returns empty \`matches[]\` and
  \`observations[]\`. The page must show the active revision and its selected
  package versions together with an explicit per-user V2 migration prompt.
  Historical V1 projection/change rows remain append-only; suppression is only
  a response-surface rule. SSE \`reset\` triggers the same principal-scoped
  full GET correction and never promotes a legacy row into either V2 surface.

The additive 081 schema gate initially leaves V1 \`active\` and registers V2 as
\`selectable\`; that is the compatibility phase, not the final grandfathered
catalog state. Strategy-selection writes must remain quiesced from the start of
081 until the V2-compatible Web, bounded evaluator, and rollback tooling are
attested. The owner-only 083 activation gate then atomically changes V1 to
\`grandfathered\`, V2 to \`active\`, and package 1 V2 to the future-principal
default, without changing any existing selection revision. It may run only
after the selection write window is quiesced and 081/082 are verified.

Per-user rollback is also versioned and fail-closed. The owner-only 082 gate can
either abandon one failed pending V2 revision while preserving its active V1
predecessor, or create one pending V1 compensation revision from the nearest
passed V1 ancestor of one active V2 revision. The bounded evaluator must replay
and atomically activate that compensation before any evaluator/Web release is
rolled back. PUBLIC, Web, evaluator, executor, quote-writer, and AI roles receive
no EXECUTE privilege on these owner-only compensation functions.

## 6. Scheduler boundary

The canonical scheduler remains single-scope:

\`\`\`text
max_scopes_per_tick=1
pending_scope_order=selection_revision_id,principal_id,user_id
pending_precedes_active=true
active_scope_cursor_mode=persistent_round_robin
transaction_scope=single_principal_user_revision
all_users_transaction=false
time_driven_active_scope_poll=true
\`\`\`

The active-scope round robin is required even when source watermarks are
unchanged so a fresh row can become stale without a new event. Each tick still
evaluates at most one principal/user/revision.

This strategy contract does not itself authorize installing, reloading,
kickstarting, or rebinding a LaunchAgent. Activation requires the exact current
Kernel policy, immutable release proof, current-open-trade-date canary, and
independent fail-closed readiness evidence.

## 7. Determinism and rollback

The projection hash must bind selected event ids, direction, trading-minute
span, coherence level, confirmation/stale evidence, market-heat evidence,
membership as-of provenance, strategy version, and policy hash. Input order or
duplicate identical events must not change the result.

Stop new Shadow evaluation and restore the prior immutable release if any of the
following occurs:

- direction or timestamp lineage cannot be proved;
- trading-minute boundary tests fail;
- membership as-of is ambiguous;
- replay is non-deterministic or creates a duplicate projection;
- the single-scope scheduler boundary is violated;
- any proposal, order, trade, position, lot, cash, autonomous, real-trading, or
  N1–N5 side effect is observed.

Historical Strategy Center projection/change evidence is append-only and must
not be deleted or rewritten during rollback. Release rollback order is: quiesce
selection writes and the scheduler, compensate each affected user if needed,
prove V1 active/passed with no pending revision and an SSE reset, then rebind to
an explicitly 081-compatible immutable release. A pre-081 release must never be
restored over active V2 revisions.
