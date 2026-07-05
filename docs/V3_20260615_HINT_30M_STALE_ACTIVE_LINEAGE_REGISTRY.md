# V3 20260615 HINT 30m Stale Active Lineage Registry

Result: `STALE_REGISTRY_PASS`

Target:
- `board:TDX:881470`
- `20260615 09:31`
- `BUY_HINT`
- stale mark: `30m_volume`

Corrected metric:
- `current_30m_virtual_amount=2348930635.56391`
- `previous_day_same_window_amount=2613103496`
- `amount_pass=false`
- `policy_version=previous_day_same_window_elapsed_ratio_v1`

Active policy:
- Historical rows are not deleted or rewritten.
- Active N6 user-message reads exclude reviewed stale source action runs.
- N6 projection dry-run blocks reviewed stale source action runs before projection.

Stale source action runs:
- `v3_n5_action_replay_20260615_after_n4_full_universe_trigger_v1`
- `v3_n5_action_replay_20260615_after_n4_formal_proof_enrichment_v1`
- `v3_n5_action_replay_20260615_attachment_rule_canonical_v1`

Boundary:
- No database write.
- No rollback.
- No outbox/inbox/checkpoint consume or update.
- No scheduler or worker start.
- No voice/mobile/sim/position/order/real trade path touched.
