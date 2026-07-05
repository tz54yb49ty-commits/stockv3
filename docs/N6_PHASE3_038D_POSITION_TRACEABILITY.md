# N6 Phase 3 038D Position Traceability

Status: DRAFT_PASS

Coverage: 24/24 rules mapped.

| rule_id | source | requirement | evidence | test_target | status |
|---|---|---|---|---|---|
| N6VA038D-001 | 038D scope | Create only position and position event | SQL has two CREATE TABLE statements | create table count test | draft |
| N6VA038D-002 | 038D scope | Do not create PnL table | SQL lacks `n6_virtual_pnl_snapshot` CREATE | future table absence scan | boundary |
| N6VA038D-003 | position | Position FK to virtual account | `virtual_account_id` FK | FK static scan | draft |
| N6VA038D-004 | position | Position principal composite FK | `(principal_id, principal_type)` FK | principal FK scan | draft |
| N6VA038D-005 | position | Position required fields present | SQL field list | field presence test | draft |
| N6VA038D-006 | position | Principal type excludes system | CHECK allows admin/human_user/ai_user | enum test | draft |
| N6VA038D-007 | position | Position status values virtual-only | status CHECK values | status enum test | draft |
| N6VA038D-008 | position | Quantities are non-negative | quantity CHECK constraints | quantity test | draft |
| N6VA038D-009 | position | Quantity equals available plus locked | equality CHECK | quantity consistency test | draft |
| N6VA038D-010 | position | Average cost non-negative | average_cost CHECK | cost test | draft |
| N6VA038D-011 | position | Last virtual trade reference only | nullable FK to n6_virtual_trade | FK static scan | draft |
| N6VA038D-012 | position | No real position fields | no forbidden field names | static scan | boundary |
| N6VA038D-013 | event | Event FK to virtual account | `virtual_account_id` FK | FK static scan | draft |
| N6VA038D-014 | event | Event principal composite FK | `(principal_id, principal_type)` FK | principal FK scan | draft |
| N6VA038D-015 | event | Event optional FK to position | nullable `virtual_position_id` FK | FK static scan | draft |
| N6VA038D-016 | event | Event source order/trade lineage | nullable source FKs to 038C tables | FK static scan | draft |
| N6VA038D-017 | event | Event type values defined | event_type CHECK values | enum test | draft |
| N6VA038D-018 | event | Quantity/cost deltas may be signed | no non-negative CHECK on deltas | delta scan | draft |
| N6VA038D-019 | event | Event table immutable by contract | no `updated_at` field | immutable scan | boundary |
| N6VA038D-020 | boundary | No T+1 rule encoded | only available/locked fields reserved | deferred rule scan | boundary |
| N6VA038D-021 | boundary | No broker/real trade/common_position/user_sim references | no forbidden references | static scan | boundary |
| N6VA038D-022 | rollback | Hard-fail before DROP | rollback DO block | rollback order test | rollback_draft |
| N6VA038D-023 | rollback | Block if position/event or future PnL rows exist | row_count guards | rollback guard test | rollback_draft |
| N6VA038D-024 | rollback | Drop only 038D tables | DROP table list | rollback scope test | rollback_draft |

Remaining gaps:

- No DDL executed.
- No live DB proof.
- No position rows.
- No position event rows.
- No PnL table.
- No T+1 execution policy.
- No position runner.
