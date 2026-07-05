# N6 Phase 3 038E PnL Static Tests

Status: DRAFT_PASS

These checks validate the 038E draft without executing DDL or writing database rows.

## SQL Static Scan

- `CREATE TABLE` count must be 1.
- Created table must be only `n6_virtual_pnl_snapshot`.
- SQL must not include business DML: `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `COPY`.
- SQL must not alter old tables.
- SQL must not include `DROP`.
- SQL must not include `GRANT`.
- SQL must not include leaderboard, AI evaluation, strategy ranking, real performance, live price, raw K, or investment advice fields.

## Model Static Checks

- `n6_virtual_pnl_snapshot` must include virtual account ownership fields.
- `n6_virtual_pnl_snapshot` must include principal composite owner fields.
- `source_cash_snapshot_id` must be nullable FK to `n6_virtual_cash_snapshot`.
- `source_price_policy` must be required and constrained to approved values.
- `valuation_policy_version` and `valuation_policy_hash` must be required.
- `net_pnl = gross_pnl - total_fee - total_tax` must be checked.
- `total_asset_value = cash_value + position_market_value` must be checked.
- `total_fee` and `total_tax` must be non-negative.
- Asset value fields must be non-negative.

## Source Boundary Static Checks

- No live price direct source.
- No raw K recomputation source.
- No N1 raw facts source.
- No N3 raw facts source.
- No broker account/funds/position source.
- `source_price_policy` is required.

## Rollback Static Scan

- Rollback must include `RAISE EXCEPTION` before the first `DROP TABLE`.
- Rollback must block if `n6_virtual_pnl_snapshot` has rows.
- Rollback must not use `CASCADE`.
- Rollback must drop only `n6_virtual_pnl_snapshot`.
- Rollback must not touch 038A/038B/038C/038D/036/037 objects.
- Rollback must not touch N1-N6 facts or outbox.
