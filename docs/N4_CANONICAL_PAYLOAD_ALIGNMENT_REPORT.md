# N4 Canonical Payload Alignment Report

## Result

- result: `DRY_RUN_PASS`
- layer_role: `N4_trigger`
- canonical spec: `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`
- mapper: `src/ashare_v3/trigger/canonical_signal.py`

## Canonical Payload

New N4 dry-run / execute payloads use only these runtime `signal_type` values:

- `B_BUY`
- `S_SELL`
- `BUY_HINT`
- `SELL_HINT`

30m information is carried by `action_mark`:

- `normal`
- `30m_volume`
- `30m_shrink`

The former 30m names are retained only as trace/audit values through `legacy_signal_type` and `original_condition_key`; they are not emitted as new runtime `signal_type`.

## Mapping

- `B_BUY -> B_BUY + normal`
- `S_SELL -> S_SELL + normal`
- `B_BUY_30M_VOL -> B_BUY + 30m_volume`
- `S_SELL_30M_SHRINK -> S_SELL + 30m_shrink`
- `BUY_HINT + projection_30m_type=volume_up -> BUY_HINT + 30m_volume`
- `SELL_HINT + projection_30m_type=shrink_down -> SELL_HINT + 30m_shrink`

## Updated Surfaces

- `projection_matcher` dry-run plans now include `signal_type`, `action_mark`, `original_condition_key`, `legacy_signal_type`, and `match_basis`.
- `projection_matcher_execute` payload/dedup contract now includes `action_mark` and `original_condition_key`.
- `local_trigger_dry_run`, `synthetic_dry_run`, and `c3_replay_plan` now emit canonical signal payloads while retaining legacy trace fields.
- 20260528 standard trigger execute contract/preflight artifacts now report canonical pending signal distribution plus legacy trace distribution.
- 20260525 projection matcher execute contract/preflight artifacts now expose canonical payload fields; execute remains blocked because this run already exists and source events are checkpointed.
- 20260528 local trigger dry-run, 20260525 projection matcher dry-run refresh, synthetic/sample dry-run, and C3 replay dry-run artifacts were refreshed in read-only mode.

## Boundary

No database/schema migration was performed. No N4/N5/N6 execute ran. No outbox, inbox, checkpoint, trigger_match, or trigger_state rows were written. No worker was started and no market data was pulled.

## Gate

Runtime remains `BLOCKED`. The next allowed step is N4 v2 execute runner contract/preflight refresh using canonical payloads. N5 dry-run remains blocked until a canonical N4 outbox execute exists and is separately reviewed.
