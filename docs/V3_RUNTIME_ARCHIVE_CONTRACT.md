# V3 Runtime Archive Contract

Result: `CONTRACT_PASS`

This contract freezes the first N3-N6 runtime archive shape:

- Hot runtime remains local SSD PostgreSQL.
- Cold archive root is `/Volumes/MacRaid/stock_db_archive/v3_runtime`.
- Archive layout is `trade_date=YYYYMMDD/{n3,n4,n5,n6}/{table}.parquet`.
- Manifest path is `trade_date=YYYYMMDD/manifests/archive_manifest.json`.
- Initial cleanup is manual-gate only.

The N6 page `/n6/archive-status` and API `/api/n6/ui/v1/archive-status` are read-only and expose no execute, cleanup, or rollback controls.

Forbidden scope: no database write, no archive file write, no local cleanup, no outbox consumption, no worker, no N6 delivery/voice/mobile/sim/position/real trade.
