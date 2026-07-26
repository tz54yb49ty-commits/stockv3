# N6 AI 投资员策略政策 V1 Shadow Canonical

```text
document_id=N6_AI_INVESTOR_STRATEGY_POLICY_V1_SHADOW_CANONICAL
document_status=APPROVED_FOR_SHADOW_ONLY
authority_status=ADMIN_SINGLE_APPROVAL_20260721
layer_role=N6_user
strategy_version=n6_ai_investor_strategy_policy_v1_shadow_20260721
implementation_status=SHADOW_ONLY_ACTIVATION_AUTHORIZED
autonomous_trading_authorized=false
real_trading_authorized=false
proposal_authorized=false
order_authorized=false
trade_authorized=false
unresolved_semantic_count=0
```

## 1. Canonical semantic source

The immutable semantic source remains:

```text
docs/N6_AI_INVESTOR_STRATEGY_POLICY_V1_DRAFT.md
sha256=56082554c4f1099c9fa265d80f0233fde7459d2748be4c85f69fc198bddfc9e7
```

This canonical document promotes that frozen semantic blob for Shadow-only
evaluation. It does not rewrite its contents or change its hash.

The approved candidate package is:

```text
docs/N6_AI_INVESTOR_STRATEGY_POLICY_V1_SHADOW_CANDIDATE_PACKAGE_20260721.json
```

## 2. Knowledge authority

```text
runtime_semantic_source_bundle=N6_AI_KNOWLEDGE_BUNDLE_V3
runtime_semantic_source_bundle_sha256=95098b11e8cc9296d243c54a8a7954aaf42f7fa4771f251b537522e1ff94332b
research_promotion_bundle=N6_AI_KNOWLEDGE_BUNDLE_V5
research_promotion_bundle_supersedes=2b4d82a8f82c0930c22872c1e097910857378ab10bbf62840f838016bf89bfd9
```

V5 is the research-room and Obsidian promotion bundle. Its manifest hashes
this canonical document and the candidate package, so its resulting bundle
and manifest hashes are recorded downstream in release/activation closeout
evidence rather than embedded here.

The Shadow runtime continues to validate the frozen V3 semantic bundle. V5,
the V3 runtime semantic bundle, the production knowledge bundle, and this
Shadow activation authority remain separate identities. This promotion does
not silently change the database evaluator or the runtime semantic bundle
pin.

## 3. Runtime scope

The approved runtime scope is limited to:

```text
open trading dates only
10:25 / 11:25 / 13:55 / 14:55 Asia/Shanghai
five-minute recovery window per slot
DeepSeek pseudonymous identity probe before private context load
at most one decision call when the slot has new eligible input
read-only Shadow decisions and audit evidence
```

The schedule and database preflight contract is:

```text
docs/N6_AI_SHADOW_OPEN_TRADE_DATE_FOUR_SLOTS_067_CONTRACT.json
```

## 4. Hard prohibitions

This promotion does not authorize:

```text
modifying N1-N5
creating proposal, order, or trade
autonomous trading
real trading
voice or mobile delivery
bypassing the open-date, slot, identity, or manifest gates
concurrent manual invocation
```

Any boundary violation invalidates the activation and requires fail-closed
rollback.

## 5. Rollback rule

Rollback restores the previous LaunchAgent/release, removes only the 067
preflight function when its guarded rollback remains safe, and preserves all
audit evidence. Git history and the immutable strategy source are not
rewritten.
