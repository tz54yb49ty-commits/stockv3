# N3 B1 Board Source-Time Semantics And Event-Time Policy Fix

- result: `IMPLEMENTATION_PASS`
- layer_role: `N3_market_data`
- gate: `N3_B1_BOARD_SOURCE_TIME_SEMANTICS_AND_EVENT_TIME_POLICY_FIX_GATE`

## Root Cause

`BoardMarketDataAdapter` reads TDX board rows through `mootdx.quotes.index(frequency=9)`. The returned `datetime` represents a K-line / period label. The previous adapter exposed that value as `snapshot_time`, so B1 source-time evidence treated a board `15:00` label as trusted realtime source time. The standard outbox writer uses snapshot time as `MarketSnapshotUpdated.event_time`, creating future event-time risk before the close.

## Source-Time Semantics Decision

Default board policy is conservative:

- `raw_snapshot_time_label`: stores the TDX `frequency=9` label for trace only
- `raw_snapshot_time_semantics`: `tdx_index_frequency_9_period_label`
- `source_time_trust_level`: `untrusted_period_label`
- `observed_at` / `fetched_at`: records when the adapter observed/fetched the row
- trusted source time: none
- default handling: `P0_BLOCK_NO_OUTBOX`
- normalize to `observed_at`: disabled unless a future reviewed policy explicitly enables it

## Event-Time Policy

The raw board `15:00` label must never become `MarketSnapshotUpdated.event_time` under the default policy. If a standard outbox run sees an untrusted board time label, B1 returns `BLOCKED` with P0 before any snapshot/outbox business write.

## No-Future-Event Proof

The implementation adds `source_time_status=source_time_untrusted_label` and quality gate `n3_b1_source_time_untrusted_label`. That status blocks:

- object snapshot write
- object `MarketSnapshotUpdated` outbox write
- standard outbox run-level write phase through the atomic precheck

## Refreshed Artifacts

- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_EXECUTE_CONTRACT.md`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_EXECUTE_CONTRACT.json`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PREFLIGHT.md`
- `docs/N3_20260611_B1_MARKET_SNAPSHOT_UPDATED_STANDARD_OUTBOX_PREFLIGHT.json`

## Forbidden Scope

No B1 execute was run in this gate. No database rows were written, no outbox/inbox/checkpoint rows were consumed or updated, no worker was started, no N4/N5/N6 path was entered, and no delivery/push/voice/mobile/proposal/order/trade/sim/position/PnL/real-trade or old-system path was touched.

## Validation

- targeted realtime snapshot tests: `PASS` (`PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_market_data_realtime_snapshot_execute*.py'`, 62 tests)
- compileall: `PASS` (`python3 -m compileall scripts src tests`)
- JSON parse: `PASS`
- forbidden scope scan: `PASS`
- git diff --check: `PASS`
