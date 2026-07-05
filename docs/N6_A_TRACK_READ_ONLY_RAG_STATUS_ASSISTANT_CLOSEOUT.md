# N6 A-Track Read-Only RAG Status Assistant Closeout

Result: `CLOSEOUT_PASS`

Gate: `N6_A_TRACK_READ_ONLY_RAG_STATUS_ASSISTANT_CLOSEOUT_GATE`

Layer role: `N6_user`

## Closeout Decision

The read-only RAG status assistant v1 can be marked complete.

Recommended next gate: `NONE`

## Implementation Summary

- Helper: `src/ashare_v3/web/rag_status.py`
- Page: `/n6/rag`
- API: `/api/n6/ui/v1/rag-search`
- Navigation label: `RAG问答`
- Template: `src/ashare_v3/web/templates/n6_rag.html`
- Tests: `tests/test_n6_user_app.py`

## Capability Summary

- Artifact-first deterministic retrieval is implemented.
- The index covers local `docs/**/*.md/json`, `docs/post_close_fastlane/**/*.md/json`, and rollback SQL files.
- Large snapshot/probe-cache bodies are skipped from full text indexing.
- Answers include evidence paths.
- Fast Lane status, rerun-required, gate result, next gate, and rollback-location questions are supported when local evidence exists.
- Missing evidence must return `NO_EVIDENCE`; the assistant must not guess.

## RAG-First Policy Proof

`AGENTS.md` now includes the `RAG-first 状态问答规则`.

For project status, lineage, gate result, `rerun_required`, rollback SQL, next gate, and next-step questions, Codex must query the local read-only RAG helper or 8786 RAG artifacts before answering.

RAG is only an artifact-first read-only evidence entry point. It does not replace live verification for process status, service errors, page 404s, live DB row counts, launchd loaded status, or execute requests.

## Validation

```text
python3 -m unittest tests/test_n6_user_app.py tests/test_post_close_fastlane_oneshot.py
Ran 148 tests ... OK

python3 -m compileall src/ashare_v3/web src/ashare_v3/runtime scripts tests
PASS

git diff --check
PASS
```

RAG helper probe:

```text
query = 20260616到20260617 N1-N2-N3A1完成了吗
answer_status = ANSWERED
top_evidence = docs/post_close_fastlane/20260617/00_status.json
top_result = EXECUTE_PASS
```

Runtime visibility proof after 8786 restart:

```text
GET /n6/rag -> 303 /n6/login
GET /api/n6/ui/v1/rag-search without session -> unauthorized
```

## Limitations

- Not a general chatbot.
- Not semantic embedding search.
- No OpenAI API.
- No external LLM.
- No secret read.
- No live DB query.
- No runtime process inspection inside RAG.
- No execute, retry, repair, rollback, or worker action.

## Forbidden Scope Proof

- Database write: `false`
- SQL executed: `false`
- N1/N2/N3 executed: `false`
- N4/N5/N6 runtime entered: `false`
- Worker started: `false`
- Outbox/inbox/checkpoint consumed or updated: `false`
- Rollback executed: `false`
- Delivery/push/voice/mobile: `false`
- Sim/position/pnl/order/real trade: `false`
- External LLM or embedding provider called: `false`
- Secret read: `false`

## Remaining Caveats

- RAG answers are artifact-based only and must cite local evidence.
- Runtime/service/database questions still require live verification.
- The repository has substantial pre-existing modified/untracked files; this closeout does not clean, stage, or commit them.

