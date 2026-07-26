# N6 B轨 AI 模拟投资员 v1 系统指南

Status: `IMPLEMENTATION_DRAFT`

Layer authority: `N6_user`

## 1. Purpose

N6 AI Agent v1 is an experimental, paper-only investor. It may read approved
shared N6 material and its own N6 virtual account, generate structured
decisions, and—only after a separate activation gate—submit policy-confirmed
virtual proposals to the existing N6 virtual executor.

It never connects to a broker, never creates a real order, and never writes
N1–N5 facts. The objective is risk-constrained simulated return, not a promise
of profit or investment advice.

## 2. Shared-signal boundary

The AI never reads a human user's projection as if it were shared. In
particular, the implementation must not relabel or reinterpret a
human-private `user_signal_projection` row by changing its
`permission_scope`, principal, user, session, monitor, or realtime-scope
meaning.

The only AI signal source is the dedicated, sanitized
`n6_ai_shared_signal_projection` table. Its producer accepts a source row only
when the source projection run:

- is a passed `N5_action` projection run; and
- carries the explicit, passed `b_track_signal_projection` producer marker.

The capture function copies only the approved signal facts needed by the AI.
It does not copy user ID, profile, session, principal, monitor, realtime-scope,
account, proposal, or other human-private fields. The shared row keeps the
true source event time from the approved source event payload; projection
insert time is not substituted for event time. Source run, event, outbox, and
projection IDs remain available only as audit references.

Current-trade-date stock rows may be trading evidence. Index and board rows
are context only and can never become a tradable identity. Source status,
trade date, direction, identity, and evidence references are revalidated
before any proposal is created.

## 3. Read and authority boundary

Allowed:

- current approved facts in `n6_ai_shared_signal_projection`;
- the AI principal's own virtual account, cash, positions, lots, quotes,
  proposals, orders, trades, PnL snapshots, decisions, and summaries;
- passed quote projections used under the valuation rules below;
- approved, versioned N6 system, policy, model-I/O, risk, and runbook
  documents.

Forbidden:

- human users' sessions, monitor rows, realtime-scope rows, proposals,
  accounts, cash, positions, orders, trades, or private projections;
- N1–N5 raw or internal tables, raw K data, event outbox, inbox, or
  checkpoints;
- arbitrary SQL, arbitrary repository files, direct market-provider access,
  broker credentials, and real-trade APIs.

The database role `n6_ai_agent` receives execution on approved hardened
functions only. It receives no direct table or sequence privilege. The Agent
cannot write order, trade, position, lot, cash, quote, projection, monitor, or
realtime-scope facts. Final virtual account writes remain exclusive to
`n6_virtual_executor`.

## 4. Frozen context and decision contract

The model adapter receives one immutable JSON context snapshot and must return
one strict object:

```json
{
  "decision_type": "buy|sell|hold",
  "identity_key": "stock:SH:600000",
  "source_signal_projection_id": "decimal-string-or-null",
  "source_virtual_position_id": "decimal-string-or-null",
  "confidence": "0..1 decimal string",
  "reason_summary": "short user-visible explanation",
  "evidence": [],
  "counter_evidence": [],
  "risk_assessment": {},
  "strategy_candidate_notes": null
}
```

The model cannot select the principal, user, account, trade date, price,
quantity, quote, execution status, server policy, or risk result. Unknown
keys, non-finite numbers, malformed bigint values, missing evidence, and
references not present in the frozen context fail closed.

The decision input hash is derived from the server-frozen context snapshot.
The submitted input hash must match it. The hardened database function
computes the canonical output hash; it does not trust a model-supplied output
hash. Server risk columns and server policy results are authoritative even
when the model supplies a different `risk_assessment`.

Only concise structured reasons, approved evidence references, and
counter-evidence are persisted for audit. Hidden model reasoning, raw prompts,
secrets, and provider credentials are never persisted or shown.

## 5. Valuation and trading policy

Valuation is fail closed:

- Decision and proposal risk use finite, positive, passed, fresh
  `v_n6_virtual_quote_latest` rows for every open position.
- Active-session quotes must satisfy the configured freshness bound.
- A daily summary uses a same-day passed closing-window quote from
  `14:55–15:05` for every open position.
- The public account view uses the approved active-session, midday-break, or
  completed-open-date closing quote policy.
- A missing, stale, invalid, non-finite, non-positive, BJ, or mismatched quote
  makes the affected valuation `not_ready`; the Agent must not infer a value
  from a stored position market-value field.

Trading rules:

- Tradable universe: Shanghai and Shenzhen stocks only.
- Buy source: a current-open-trade-date shared N6 stock buy signal.
- Sell source: an AI-owned open position plus a current shared sell signal,
  deterministic stop loss, or portfolio-risk liquidation.
- Fill source: a fresh, passed N3N6Q quote selected by the N6 executor.
- Settlement: T+1 and 100-share lot rules remain authoritative.
- Per buy: at most CNY 300,000.
- Per identity: at most CNY 600,000 exposure.
- Total gross exposure: at most 10% of current account equity.
- Daily new buys: at most 10; the first three autonomous canary days allow one.
- Drawdown pause: 5% from the high-water mark.

Open AI buy proposals in `confirmed` or `processing` state reserve their
server-owned buy budget. Those reservations are included in cash, per-identity,
and total-exposure checks so concurrent decisions cannot spend the same
capacity. Current equity and drawdown are recomputed from fresh quote
valuations when the proposal is created and again inside the executor
transaction. A model decision cannot bypass either check.

When effective drawdown reaches 5%, the authority function persistently
changes the AI user to `status=disabled`. This is not a transient runner
message: autonomous decisions and proposals remain disabled until an explicit
review and recovery gate changes the status. Existing positions remain
visible and deterministic quote, executor, and stop services keep their own
independent contracts.

## 6. Runtime modes

The runner has three explicit modes:

- `disabled`: no model call, decision, or proposal write;
- `shadow`: context and decision/report facts may be recorded, but proposals
  are forbidden;
- `autonomous_canary`: an eligible decision may create one confirmed virtual
  proposal through the dedicated risk-gated function.

The default is `disabled`. Missing or contradictory mode configuration is
treated as disabled. The model adapter is called only for a changed input
snapshot and at most once per five-minute trading bucket.

An AI user persistently disabled by the drawdown gate remains ineligible for
model and proposal execution even if the process mode says
`autonomous_canary`. The daily-summary path remains permitted after 15:15 so
the disabled day, account result, pause reason, and next-day review can still
be frozen without re-enabling trading.

Model timeout, invalid output, repository failure, stale input, unavailable
quote, or policy failure produces no proposal. The Agent, executor, quote
writer, stop evaluator, and daily-summary runner remain independently
pausable services.

## 7. Daily summary and controlled evolution

At 15:15 or later on an open trade date, the daily-summary runner records one
idempotent summary after closing valuation is ready. It freezes:

- strategy ID, version, and hash;
- knowledge-bundle version and hash;
- closing account snapshot and its hash;
- total assets, available cash, market value, and actual daily PnL;
- cumulative net return, maximum drawdown, turnover, and risk-adjusted score;
- decision count and actual buy/sell trade counts;
- trade review, success-reason, failure-reason, and next-day-watch arrays;
- a concise user-visible summary.

Daily PnL is the change from the previous frozen daily account result; it is
not mislabeled cumulative return. The score is:

```text
net_return_pct - 1.5 * max_drawdown_pct - 0.02 * turnover_pct
```

The AI may record internal candidate-strategy notes and propose a candidate
strategy version, but it cannot activate one. A candidate needs deterministic
historical replay, at least ten open trading days in shadow mode, and explicit
administrator promotion. Production code, documents, permissions, prompts,
and policies are never self-modified.

## 8. Public B-track display

Every authenticated B-track user may read the same public AI account page:

- account equity, cash, quote-derived exposure, return, and drawdown;
- positions and virtual trades;
- concise structured decision reasons, approved evidence, counter-evidence,
  risk checks, and execution status;
- daily summaries, frozen strategy version, model adapter version, and Agent
  status, including a drawdown pause.

The page and APIs are GET-only. They provide no proposal, confirmation, pause,
strategy-edit, account-edit, or AI-status control.

The public reader requires exactly one eligible shared AI actor. A drawdown-
disabled AI remains readable so its decisions and account history stay
auditable. Stock display names come only from the sanitized shared N6 signal
projection. Authority or repository failures return a stable unavailable
response and never expose stored failure details.

The public surface must not expose:

- hidden reasoning or chain of thought;
- raw prompts, model credentials, service credentials, or secret paths;
- internal strategy candidate notes;
- human-private user, session, principal, monitor, realtime-scope, account,
  proposal, position, or projection fields.

Invalid public valuation is shown as `not_ready` with null aggregate equity
rather than a fabricated number.

## 9. Research room, public snapshot, and memory boundary

The administrator-only `N6 AI 投资员研究室` is not the production Agent. It
has no database credential, proposal authority, executor authority, model API
key, runtime-control capability, or external-network research capability.

One independent five-minute one-shot publisher connects only as
`n6_ai_agent`, starts a read-only transaction, verifies
`session_user=current_user=n6_ai_agent`, and calls only
`n6_btrack_ai_public_snapshot(repeat('0',64),50,50,30)`. The function exposes
the same sanitized shared AI account that authenticated B-track users can
read. The publisher applies the public Web model and strict public-snapshot
schema again, then atomically replaces only:

```text
40-AI投资员/30-决策与日报/ai_public_snapshot.json
```

The target is a nonempty regular file owned by the current operating-system
user with exact mode `0600`. Parent directories must be owner-controlled and
not group/world writable. Symlinks, FIFOs, unexpected owners or modes,
alternate paths, password/DSN environment values, owner database identities,
and non-read-only transactions fail closed. The publisher has no OpenAI key
and cannot create decisions, proposals, orders, trades, positions, or cash
facts.

The local research MCP reads that file dynamically, so account updates do not
require rebuilding the immutable knowledge manifest. Its manifest binds the
fixed root, fixed relative path, and `dynamic_owner_0600_v1` mode; every tool
call revalidates the current file owner, mode, type, size, JSON schema, public
scope, and read-only marker before returning it.

Long-term memory remains split:

- immutable Git documents and field dictionaries are semantic authority;
- database context, decision, proposal, trade, position, and summary facts are
  episodic authority;
- Obsidian candidate memories are append-only research notes;
- temporary retrieval output is working memory.

Candidate memories cannot change production prompts, policies, code,
permissions, knowledge bundles, or trading behavior. Promotion requires an
explicit administrator review and a new versioned Git knowledge-bundle gate.
The production Agent never reads the repository or Obsidian.

## 10. Rollback

Runtime rollback disables the AI Agent and restores the previous immutable Web
or runner release. It does not delete decisions, summaries, proposals, orders,
trades, positions, cash history, quote history, or PnL history.

Schema rollback is permitted only when all AI identity/account state, AI
business history, AI execution/valuation history, dependent runtime, and
restricted-role activity are zero. Under that precondition it may remove the
shared-projection capture trigger, sanitized backfill table, 055 functions,
grants, tables, columns, and constraints while preserving schemas 041–054.
The shared projection is classified as rebuildable derived data, not business
history, only while every row still matches an approved, passed N6 projection
run and its complete sanitized source fields and payload hash. The rollback
locks both source and derived relations before checking. Any orphan row,
unapproved producer, changed source, payload mismatch, non-active derived
status, or other field drift blocks the rollback.

If any AI history exists, rollback must fail closed. It must not drop the
shared trigger/table or erase facts; the safe response is to disable Agent
runtime/functions and preserve the audit trail.
