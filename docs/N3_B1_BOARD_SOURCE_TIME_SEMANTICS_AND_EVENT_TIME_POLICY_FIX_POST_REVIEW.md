# N3 B1 Board Source-Time Semantics And Event-Time Policy Fix Post-Review

- post_review_result: `POST_REVIEW_PASS`
- layer_role: `N3_market_data`
- gate: `N3_B1_BOARD_SOURCE_TIME_SEMANTICS_AND_EVENT_TIME_POLICY_FIX_POST_REVIEW_GATE`

## Reviewed Inputs

- `docs/N3_B1_BOARD_SOURCE_TIME_SEMANTICS_AND_EVENT_TIME_POLICY_FIX.md`
- `docs/N3_B1_BOARD_SOURCE_TIME_SEMANTICS_AND_EVENT_TIME_POLICY_FIX.json`
- `src/ashare_v3/market/realtime_snapshot_execute.py`
- `tests/test_market_data_realtime_snapshot_execute.py`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_EXECUTE_CONTRACT.md`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_EXECUTE_CONTRACT.json`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PREFLIGHT.md`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PREFLIGHT.json`

## Semantics Proof

Implementation result is `IMPLEMENTATION_PASS`.

`BoardMarketDataAdapter` no longer exposes `mootdx.quotes.index(frequency=9)` `datetime` as trusted `snapshot_time`. It stores the value as trace:

- `raw_snapshot_time_label`
- `raw_snapshot_time_semantics=tdx_index_frequency_9_period_label`
- `source_time_trust_level=untrusted_period_label`
- `observed_at`
- `fetched_at`

## Event-Time Policy Proof

Default board policy is conservative:

- default handling: `P0_BLOCK_NO_OUTBOX`
- normalize to observed_at: `false`
- trusted realtime source time field: none
- event-time policy: `do_not_use_raw_snapshot_time_label_as_market_snapshot_updated_event_time`

Therefore a board raw `15:00` period label before 15:00 is classified as `source_time_untrusted_label`, not `source_time_future` and not `source_time_confirmed`.

## No-Future-Event Proof

The `source_time_untrusted_label` path writes no passed snapshot and no `MarketSnapshotUpdated` outbox row.

- object status: `failed`
- quality severity: `P0`
- quality gate: `n3_b1_source_time_untrusted_label`
- object snapshot rows: `0`
- object outbox rows: `0`

The standard outbox run-level atomic precheck counts untrusted labels and blocks before `common_market_data_run`, snapshot, quality, or outbox business writes. This prevents stock/index partial writes when board semantics are not trusted.

## Contract / Preflight Proof

The 20260611 B1 standard outbox contract and preflight include:

- `source_time_policy.board_source_time_label_handling=P0_BLOCK_NO_OUTBOX`
- `board_source_time_semantics_policy.enabled=true`
- `board_source_time_semantics_policy.raw_datetime_semantics=tdx_index_frequency_9_period_label`
- `board_source_time_semantics_policy.normalize_to_observed_at_enabled=false`
- `board_source_time_semantics_policy.quality_gate=n3_b1_source_time_untrusted_label`
- `run_level_atomic_source_time_precheck.enabled=true`

## Remaining Route Decision

The implementation fixes future-event risk and partial-write risk, but the default board policy means a standard outbox retry before trusted board realtime source time exists will safely block with no writes. N4 still needs a policy decision before it can receive complete stock/index/board `MarketSnapshotUpdated` input:

- either accept a reviewed normalization policy using `observed_at`
- or use a different trusted board realtime source
- or allow stock/index-only outbox with explicit board exclusion policy

This post-review does not choose that route.

## Forbidden Scope

No B1 execute happened in this post-review gate. No database writes, no outbox/inbox/checkpoint mutation, no worker, no N4/N5/N6, no delivery/push/voice/mobile, no proposal/order/trade, no sim/position/PnL/real trade, and no old-system touch.

## Validation

- targeted tests: `PASS` (`PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_market_data_realtime_snapshot_execute*.py'`, 62 tests)
- compileall: `PASS` (`python3 -m compileall scripts src tests`)
- JSON parse: `PASS`
- forbidden scope scan: `PASS`
- git diff --check: `PASS`

## Decision

`POST_REVIEW_PASS`.

Do not go directly to B1 standard outbox retry final gate under the current default board policy. The default policy will safely `BLOCK_NO_OUTBOX` for untrusted board period labels, so N4 still needs a board event route decision first.

Recommended next gate: `N3_20260611_B1_BOARD_MARKET_SNAPSHOT_UPDATED_EVENT_ROUTE_DECISION_GATE`.
