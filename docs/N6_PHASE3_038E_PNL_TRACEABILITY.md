# N6 Phase 3 038E PnL Traceability

Status: DRAFT_PASS

Coverage: 22/22 rules mapped.

| rule_id | source | requirement | evidence | test_target | status |
|---|---|---|---|---|---|
| N6VA038E-001 | 038E scope | Create only PnL snapshot table | SQL has one CREATE TABLE statement | create table count test | draft |
| N6VA038E-002 | 038E scope | Do not create leaderboard/AI/strategy ranking tables | SQL lacks those CREATE statements | future table absence scan | boundary |
| N6VA038E-003 | PnL | FK to virtual account | `virtual_account_id` FK | FK static scan | draft |
| N6VA038E-004 | PnL | Principal composite FK | `(principal_id, principal_type)` FK | principal FK scan | draft |
| N6VA038E-005 | PnL | Required fields present | SQL field list | field presence test | draft |
| N6VA038E-006 | PnL | Source cash snapshot lineage | nullable FK to cash snapshot | FK static scan | draft |
| N6VA038E-007 | PnL | Source price policy required | NOT NULL and CHECK values | policy enum test | draft |
| N6VA038E-008 | PnL | Valuation policy fields required | NOT NULL version/hash | valuation policy test | draft |
| N6VA038E-009 | PnL | Net PnL formula enforced | CHECK net formula | formula test | draft |
| N6VA038E-010 | PnL | Asset value formula enforced | CHECK total asset formula | formula test | draft |
| N6VA038E-011 | PnL | Fee/tax non-negative | CHECK constraints | amount test | draft |
| N6VA038E-012 | PnL | Asset values non-negative | CHECK constraints | value test | draft |
| N6VA038E-013 | PnL | PnL status values virtual-only | status CHECK values | status enum test | draft |
| N6VA038E-014 | boundary | No live price/raw K fields | no forbidden field names | static scan | boundary |
| N6VA038E-015 | boundary | No brokerage/performance/advice fields | no forbidden field names | static scan | boundary |
| N6VA038E-016 | boundary | No fee/tax/T+1 hardcoded rules | amount summaries only | deferred rule scan | boundary |
| N6VA038E-017 | boundary | No leaderboard table | no leaderboard CREATE | scope scan | boundary |
| N6VA038E-018 | boundary | No AI evaluation or strategy ranking | no AI/ranking CREATE | scope scan | boundary |
| N6VA038E-019 | boundary | PnL is virtual-only disclaimer documented | migration draft boundary section | doc scan | doc |
| N6VA038E-020 | rollback | Hard-fail before DROP | rollback DO block | rollback order test | rollback_draft |
| N6VA038E-021 | rollback | Block if PnL snapshot rows exist | row_count guard | rollback guard test | rollback_draft |
| N6VA038E-022 | rollback | Drop only 038E table | DROP table list | rollback scope test | rollback_draft |

Remaining gaps:

- No DDL executed.
- No live DB proof.
- No PnL rows.
- No PnL runner.
- No approved leaderboard gate.
- No valuation policy runner.
