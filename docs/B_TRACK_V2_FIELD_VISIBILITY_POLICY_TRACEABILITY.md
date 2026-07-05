# B Track V2 Field Visibility Policy Traceability

Gate: `B_TRACK_V2_FIELD_VISIBILITY_POLICY_DESIGN_GATE`  
Layer role: `runtime_control`  
Status: `DESIGN_PASS`

## Rule Coverage

| Rule ID | Requirement | Design coverage | Status |
|---|---|---|---|
| FV-01 | B-track source remains `v_n6_*` readonly views | Official source list names only the five views | covered |
| FV-02 | UI/API source label may remain `n6_display_*_cache` | Logical labels preserved separately from physical sources | covered |
| FV-03 | Do not read base display basis tables | Base tables listed under forbidden sources | covered |
| FV-04 | Do not use experimental local display cache | `n6_*_display_cache` physical tables forbidden | covered |
| FV-05 | Do not fanout rows | Policy does not alter row grain or mapping | covered |
| FV-06 | Do not semantically rewrite N2 fields | Policy classifies visibility only | covered |
| FV-07 | Do not read raw K or direct live market | Forbidden source list includes both | covered |
| FV-08 | Do not bypass through N4/N5 raw facts | Forbidden source list includes raw facts bypass | covered |
| FV-09 | Do not use unreviewed outbox | Forbidden source list includes unreviewed outbox | covered |
| FV-10 | Define default list fields | Default list fields section covers common and asset-specific fields | covered |
| FV-11 | Define detail fields | Detail fields section covers summaries, policies, quality, financial summary | covered |
| FV-12 | Define audit fields | Audit fields section covers source lineage, raw trace, target trace, membership raw payload | covered |
| FV-13 | Define hidden-by-default fields | Hidden-by-default section lists raw and trace-heavy fields | covered |
| FV-14 | Define internal-only fields | Internal-only section restricts raw bodies and source id arrays | covered |
| FV-15 | `/n6/app/filter-center` scoped | Page scope section covers filter-center default/detail/audit behavior | covered |
| FV-16 | Dashboard/home helper scoped | Page scope keeps dashboard summary-oriented | covered |
| FV-17 | Future detail drawer scoped | Page scope assigns detail fields to future drawer | covered |
| FV-18 | Membership lookup scoped | Page scope hides `raw_payload` by default | covered |
| FV-19 | Signals/status/watchlist not auto changed | Page scope marks them unchanged by this gate | covered |
| FV-20 | v2 filter APIs remain compact by default | API policy says compact explicit allowlist | covered |
| FV-21 | Future `include=detail` requires separate gate | API policy reserves include mode for implementation gate | covered |
| FV-22 | Future `include=audit` requires separate gate | API policy reserves include mode for operator/audit gate | covered |
| FV-23 | Field allowlist required | API policy requires explicit field allowlist | covered |
| FV-24 | No `SELECT *` to frontend | API policy forbids `SELECT *` payloads | covered |
| FV-25 | Financial fields not investment advice | Safety wording policy requires neutral factual wording | covered |
| FV-26 | Target/score fields not future return promise | Safety wording policy frames them as trace/evidence | covered |
| FV-27 | No PnL/leaderboard/real performance fields | Page scope keeps those locked/static and not changed | covered |
| FV-28 | Forbidden wording blocked | Forbidden user-facing wording list included | covered |
| FV-29 | Source trace fields classified | Audit/hidden/internal tiers classify source trace fields | covered |
| FV-30 | Period trigger baseline classified | Detail summary, hidden raw, internal raw body tiers classify it | covered |
| FV-31 | Structural trace fields classified | Detail fields include `prev_up_str` and `prev_dn_str` | covered |
| FV-32 | Symmetry/target trace fields classified | Audit tier classifies full target trace fields | covered |
| FV-33 | Secondary anchor fields classified | Audit tier classifies up/down secondary anchor fields | covered |
| FV-34 | Structure score fields classified | Detail tier includes `level_up_score` and `level_down_score` | covered |
| FV-35 | Stock financial/risk fields classified | Default/detail/audit tiers split stock financial/risk fields | covered |
| FV-36 | Membership `raw_payload` classified | Hidden/internal/audit tier only, not default | covered |
| FV-37 | No code modification | Forbidden scope marks `code_modified=false` | covered |
| FV-38 | No database writes | Forbidden scope marks `database_written=false` | covered |
| FV-39 | No execute | Forbidden scope marks `execute_performed=false` | covered |
| FV-40 | No outbox update/consume | Forbidden scope marks `outbox_consumed_or_updated=false` | covered |
| FV-41 | No worker | Forbidden scope marks `worker_started=false` | covered |
| FV-42 | No local display cache sync/activation/rollback | Forbidden scope marks all local cache flags false | covered |
| FV-43 | No proposal/order/trade | Forbidden scope marks proposal/order/trade flags false | covered |
| FV-44 | No position/PnL update | Forbidden scope marks position/PnL flags false | covered |
| FV-45 | No real trade | Forbidden scope marks `real_trade_submitted=false` | covered |
| FV-46 | No action flow mutation | Forbidden scope marks `action_flow_mutated=false` | covered |

## Coverage Summary

```text
rule_count=46
covered=46
coverage=100%
duplicate=0
missing=0
```

## Review Notes

This traceability artifact covers design policy only. It does not authorize implementation of `include=detail`, `include=audit`, a detail drawer, an audit panel, or new SQL selectors. Those require later implementation gates.

Next gate:

```text
B_TRACK_V2_FIELD_VISIBILITY_POLICY_REVIEW_GATE
```
